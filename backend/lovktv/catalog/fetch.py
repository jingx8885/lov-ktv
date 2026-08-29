"""Compatibility facade for catalog search, lyrics, audio and importing.

Implementations live in focused modules; this module intentionally keeps the
historical symbols so callers and monkeypatch-based integrations continue to
work unchanged.
"""
from __future__ import annotations
import urllib.request
import shutil, subprocess
import hashlib, json, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from . import bilibili
from . import search as _search
from . import lyrics as _lyrics
from . import audio as _audio
from . import importer as _importer
from .search import *
from .lyrics import parse_lrc, LRC_LINE, META_PREFIX
from .audio import (
    _AUDIO_CACHE, remember_audio_source, forget_audio_source, peek_audio_source,
    probe_netease_url, open_netease_audio, try_netease_download,
    _ytdlp_download, _ytdlp_direct_url, _pick_best_match, try_ytdlp_search,
    pick_bilibili_mv, try_bilibili_download, open_bilibili_audio,
)
from .mugen import is_mugen_kid, search_mugen, import_mugen_song, pick_vocal_hit, open_mugen_preview
from .kugou import fetch_kugou_lyrics
from .netease import eapi_play_url, media_request
from .http import urlopen, curl_proxy_args, ytdlp_proxy_args

def post_form(url: str, fields: dict[str, Any], timeout: float = 15) -> bytes:
    return _search.post_form(url, fields, timeout)

def search_tonzhon(query: str, count: int = 12, source: str = "netease", page: int = 1) -> list[dict[str, Any]]:
    import json
    raw = post_form(TONZHON_API, {"types": "search", "count": count, "source": source, "name": query, "pages": max(1, int(page))})
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, list) else []

def fetch_lyric(song_id: str, source: str = "netease") -> str:
    import json
    raw = post_form(TONZHON_API, {"types": "lyric", "id": song_id, "source": source})
    obj = json.loads(raw.decode("utf-8"))
    return str(obj.get("lyric") or "")

def probe_netease_url(song_id: str) -> bool:
    return bool(eapi_play_url(song_id))

def try_netease_download(song_id, out_path):
    # Keep this seam on the facade: callers historically monkeypatch
    # ``fetch.eapi_play_url`` and ``fetch.subprocess``.
    url = eapi_play_url(song_id)
    if not url: return False
    from .http import curl_proxy_args
    cmd = ["curl", "-sL", "-o", str(out_path), "-w", "%{http_code}\n%{url_effective}\n", "-A", "Mozilla/5.0", "-e", "https://music.163.com/", *curl_proxy_args(), url]
    try: result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError): return False
    info = result.stdout.strip().splitlines(); status = info[0] if info else ""; final = info[1] if len(info) > 1 else ""
    if status.startswith("2") and "/404" not in final and out_path.exists() and out_path.stat().st_size > 50_000: return True
    if out_path.exists(): out_path.unlink()
    return False

def open_netease_audio(song_id: str, timeout: float = 20):
    url = eapi_play_url(song_id)
    if not url:
        return None
    try:
        resp = urlopen(media_request(url), timeout=timeout, via_proxy=True)
    except Exception:
        return None
    final = str(resp.geturl() or "")
    ctype = str(resp.headers.get("Content-Type") or "").lower()
    if "/404" in final or "text/html" in ctype:
        try: resp.close()
        except Exception: pass
        return None
    return resp

def _list_ytdlp(*args, **kwargs):
    return _search._list_ytdlp(*args, **kwargs)

def _tonzhon_hits(query: str, count: int, page: int) -> list[dict[str, Any]]:
    try: return search_tonzhon(query, count=count, page=page)
    except Exception: return []

def search_songs(query: str, count: int = 10, page: int = 1) -> dict[str, Any]:
    page, count = max(1, int(page)), max(1, min(int(count), 30)); extra = min(count, 5)
    with ThreadPoolExecutor(max_workers=3) as pool:
        mugen_job = pool.submit(search_mugen, query, count, page)
        bili_job = pool.submit(search_bilibili_hits, query, count, page)
        sc_job = pool.submit(search_ytdlp_hits, query, "soundcloud", extra, page)
        try: mugen = mugen_job.result()
        except Exception: mugen = {"hits": [], "has_more": False}
        try: bili = bili_job.result()
        except Exception: bili = []
        try: soundcloud = sc_job.result()
        except Exception: soundcloud = []
    groups = {"mugen": list(mugen.get("hits") or []), "bilibili": bili, "soundcloud": soundcloud}; hits = merge_channel_hits(groups, count); available = sum(len(v) for v in groups.values())
    return {"query": query, "page": page, "count": count, "has_more": bool(mugen.get("has_more")) or available > len(hits) or any(len(groups[k]) >= count for k in SEARCH_CHANNELS), "hits": hits, "sources": list(SEARCH_CHANNELS)}

def _resolve_ytdlp_source(song_id: str, title: str = "", artist: str = "", providers: tuple[str, ...] = ("soundcloud", "youtube")) -> dict[str, Any]:
    query = " ".join(p for p in (title, artist) if p).strip(); ytdlp = _audio.shutil.which("yt-dlp")
    if not ytdlp or not query: return {}
    for provider in providers:
        best = _pick_best_match(_list_ytdlp(query, ytdlp, provider, count=8))
        if best:
            page = str(best.get("url") or "")
            if page and _ytdlp_direct_url(page): return remember_audio_source(song_id, {"kind": "ytdlp", "page": page, "title": str(best.get("title") or title), "provider": provider})
    return {}

def _resolve_netease_source(song_id: str, title: str = "") -> dict[str, Any]: return _audio._resolve_netease_source(song_id, title)
def _resolve_bilibili_source(song_id: str, title: str = "", artist: str = "") -> dict[str, Any]: return _audio._resolve_bilibili_source(song_id, title, artist)

def is_preview_id(song_id: str) -> bool:
    value = str(song_id or "").strip()
    return bool(value) and (is_mugen_kid(value) or bilibili.is_bvid(value) or value.isdigit() or bool(peek_audio_source(value).get("kind")))

def resolve_audio_source(song_id: str, title: str = "", artist: str = "") -> dict[str, Any]:
    if bilibili.is_bvid(song_id):
        cached = peek_audio_source(song_id)
        if cached.get("kind") == "bilibili": return cached
        urls = bilibili.play_urls(song_id)
        if not urls.get("audio_url"): return {}
        return remember_audio_source(song_id, {"kind": "bilibili", "bvid": song_id, "title": str(urls.get("title") or title), "cover": str(urls.get("cover") or "")})
    cached = peek_audio_source(song_id)
    if cached.get("kind") == "bilibili": return cached
    if cached.get("kind") == "ytdlp" and not str(song_id).isdigit(): return cached
    if not str(song_id).isdigit(): return cached if cached.get("kind") else {}
    netease = _resolve_netease_source(song_id, title)
    if netease: return netease
    bili = _resolve_bilibili_source(song_id, title, artist)
    if bili: return bili
    if cached.get("kind") in {"netease", "ytdlp"}: return cached
    return _resolve_ytdlp_source(song_id, title, artist, ("soundcloud",)) or _resolve_ytdlp_source(song_id, title, artist, ("youtube",))

def _open_ytdlp_stream(page: str):
    direct = _ytdlp_direct_url(page)
    if not direct: return None
    try: return urlopen(urllib.request.Request(direct, headers={"User-Agent": BROWSER_UA}), timeout=30, via_proxy=True)
    except Exception: return None

def open_preview_stream(song_id: str, title: str = "", artist: str = "", media: str = ""):
    if is_mugen_kid(song_id): return open_mugen_preview(song_id, media_name=media), {"kind": "mugen", "title": title}
    source = resolve_audio_source(song_id, title, artist)
    if source.get("kind") == "bilibili":
        resp = open_bilibili_audio(str(source.get("bvid") or ""))
        if resp is not None: return resp, source
        forget_audio_source(song_id); source = _resolve_ytdlp_source(song_id, title, artist, ("soundcloud",)) or _resolve_netease_source(song_id, title) or _resolve_ytdlp_source(song_id, title, artist, ("youtube",))
    if source.get("kind") == "ytdlp" and source.get("provider") == "soundcloud":
        resp = _open_ytdlp_stream(str(source.get("page") or ""))
        if resp is not None: return resp, source
        forget_audio_source(song_id); source = _resolve_netease_source(song_id, title) or _resolve_ytdlp_source(song_id, title, artist, ("youtube",))
    if source.get("kind") == "netease":
        resp = open_netease_audio(song_id)
        if resp is not None: return resp, source
        forget_audio_source(song_id); source = _resolve_ytdlp_source(song_id, title, artist, ("youtube",))
    if source.get("kind") == "ytdlp":
        resp = _open_ytdlp_stream(str(source.get("page") or ""))
        if resp is not None: return resp, source
        forget_audio_source(song_id)
    return None, source

def _complete_mugen_audio(*args, **kwargs): return _importer._complete_mugen_audio(*args, **kwargs)
def import_song(*args, **kwargs): return _importer.import_song(*args, **kwargs)
