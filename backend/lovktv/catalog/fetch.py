"""Song search + download, following vendor/lovjpn/scripts/fetch_song.py.

Search lists Mugen, Bilibili, and SoundCloud.
Audio resolve may still fall back to NetEase / YouTube.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from lovktv.catalog import bilibili
from lovktv.catalog.http import curl_proxy_args, urlopen, ytdlp_proxy_args
from lovktv.catalog.kugou import fetch_kugou_lyrics
from lovktv.catalog.mugen import import_mugen_song, is_mugen_kid, open_mugen_preview, pick_vocal_hit, search_mugen
from lovktv.catalog.netease import eapi_play_url, media_request

TONZHON_API = "https://tonzhon.com/api.php"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
LRC_LINE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
META_PREFIX = (
    "作词",
    "作曲",
    "编曲",
    "作詞",
    "編曲",
    "制作人",
    "製作人",
    "制作",
    "Lyrics",
    "lyrics by",
    "composer",
    "arranger",
    "Producer",
    "producer",
)
BAD_TITLE_TOKENS = (
    "remix",
    "cover",
    "flip",
    "nightcore",
    "slowed",
    "reverb",
    "sped up",
    "8d",
    "karaoke",
    "カラオケ",
    "instrumental",
    "off vocal",
    "オフボーカル",
    "伴奏",
    "inst.",
    "inst ",
    "piano ver",
    "acoustic ver",
    "live at",
    "first take",
    "ザ・ファースト",
    "歌ってみた",
    "原曲歌手",
    "歌っちゃ王",
    "+1key",
    "+2key",
    "+3key",
    "-1key",
    "-2key",
    "-3key",
)


TITLE_VERSION = re.compile(r"[\s]*[\(（\[【][^\)）\]】]{0,40}[\)）\]】]")


def is_clean_title(title: str) -> bool:
    low = (title or "").lower()
    return not any(tok in low for tok in BAD_TITLE_TOKENS)


def clean_search_title(title: str) -> str:
    text = TITLE_VERSION.sub("", title or "")
    text = re.sub(r"\s+", " ", text).strip(" -_·|/")
    return text or str(title or "").strip()


def post_form(url: str, fields: dict[str, Any], timeout: float = 15) -> bytes:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": BROWSER_UA,
            "Referer": "https://tonzhon.com/",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def search_tonzhon(query: str, count: int = 12, source: str = "netease", page: int = 1) -> list[dict[str, Any]]:
    raw = post_form(
        TONZHON_API,
        {
            "types": "search",
            "count": count,
            "source": source,
            "name": query,
            "pages": max(1, int(page)),
        },
    )
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        return []
    return data


def flatten_artists(song: dict[str, Any]) -> str:
    artists = song.get("artist") or []
    names: list[str] = []
    for item in artists:
        if isinstance(item, list):
            names.extend(str(part) for part in item if part)
        elif item:
            names.append(str(item))
    return " / ".join(names)


SEARCH_CHANNELS = ("mugen", "bilibili", "soundcloud")


def _tonzhon_hits(query: str, count: int, page: int) -> list[dict[str, Any]]:
    try:
        return search_tonzhon(query, count=count, page=page)
    except Exception:
        return []


def search_bilibili_hits(query: str, count: int = 8, page: int = 1) -> list[dict[str, Any]]:
    try:
        videos = bilibili.search_videos(query, count=max(count, 12), page=page)
    except Exception:
        return []
    hits: list[dict[str, Any]] = []
    for item in videos:
        title = str(item.get("title") or "")
        bvid = str(item.get("bvid") or "")
        if not bvid or not title:
            continue
        low = title.lower()
        if any(tok in low for tok in bilibili.SKIP_TITLE):
            continue
        duration = item.get("duration")
        if isinstance(duration, int) and not (bilibili.MIN_SEC <= duration <= bilibili.MAX_SEC):
            continue
        remember_audio_source(
            bvid,
            {
                "kind": "bilibili",
                "bvid": bvid,
                "title": title,
                "cover": str(item.get("pic") or ""),
            },
        )
        hits.append(
            {
                "id": bvid,
                "title": title,
                "artist": str(item.get("author") or ""),
                "album": "",
                "pic": str(item.get("pic") or ""),
                "source": "bilibili",
                "is_mv": True,
                "clean": is_clean_title(title),
                "preview_url": f"/api/preview/{bvid}",
            }
        )
        if len(hits) >= count:
            break
    return hits


def search_ytdlp_hits(query: str, provider: str, count: int = 5, page: int = 1) -> list[dict[str, Any]]:
    if page > 1 or provider != "soundcloud":
        return []
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return []
    try:
        rows = _list_ytdlp(query, ytdlp, provider, count=count, timeout=6)
    except Exception:
        return []
    hits: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("title") or "")
        page_url = str(row.get("url") or "")
        if not page_url:
            continue
        hid = f"{provider}_{hashlib.sha1(page_url.encode('utf-8')).hexdigest()[:12]}"
        remember_audio_source(
            hid,
            {"kind": "ytdlp", "page": page_url, "title": title, "provider": provider},
        )
        hits.append(
            {
                "id": hid,
                "title": title,
                "artist": "",
                "album": "",
                "pic": "",
                "source": provider,
                "is_mv": provider == "youtube",
                "clean": is_clean_title(title),
                "preview_url": f"/api/preview/{hid}",
            }
        )
        if len(hits) >= count:
            break
    return hits


def merge_channel_hits(groups: dict[str, list[dict[str, Any]]], count: int) -> list[dict[str, Any]]:
    queues = {key: list(groups.get(key) or []) for key in SEARCH_CHANNELS}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    while len(out) < count:
        added = False
        for key in SEARCH_CHANNELS:
            bucket = queues[key]
            while bucket:
                hit = bucket.pop(0)
                hid = str(hit.get("id") or "")
                if not hid or hid in seen:
                    continue
                seen.add(hid)
                out.append(hit)
                added = True
                break
            if len(out) >= count:
                break
        if not added:
            break
    return out


def search_songs(query: str, count: int = 10, page: int = 1) -> dict[str, Any]:
    page = max(1, int(page))
    count = max(1, min(int(count), 30))
    extra = min(count, 5)
    with ThreadPoolExecutor(max_workers=3) as pool:
        mugen_job = pool.submit(search_mugen, query, count, page)
        bili_job = pool.submit(search_bilibili_hits, query, count, page)
        sc_job = pool.submit(search_ytdlp_hits, query, "soundcloud", extra, page)
        try:
            mugen = mugen_job.result()
        except Exception:
            mugen = {"hits": [], "has_more": False}
        try:
            bili = bili_job.result()
        except Exception:
            bili = []
        try:
            soundcloud = sc_job.result()
        except Exception:
            soundcloud = []
        groups = {
            "mugen": list(mugen.get("hits") or []),
            "bilibili": bili,
            "soundcloud": soundcloud,
        }
    hits = merge_channel_hits(groups, count)
    available = sum(len(bucket) for bucket in groups.values())
    return {
        "query": query,
        "page": page,
        "count": count,
        "has_more": bool(mugen.get("has_more")) or available > len(hits) or any(len(groups[key]) >= count for key in SEARCH_CHANNELS),
        "hits": hits,
        "sources": list(SEARCH_CHANNELS),
    }


def fetch_lyric(song_id: str, source: str = "netease") -> str:
    raw = post_form(TONZHON_API, {"types": "lyric", "id": song_id, "source": source})
    obj = json.loads(raw.decode("utf-8"))
    return str(obj.get("lyric") or "")


def parse_lrc(lrc: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lrc.splitlines():
        match = LRC_LINE.match(line.strip())
        if not match:
            continue
        mins, secs, text = match.group(1), match.group(2), match.group(3).strip()
        ms = int((int(mins) * 60 + float(secs)) * 1000)
        if not text or text in {"-", "—", "–"}:
            if not text:
                for item in reversed(out):
                    if item.get("end_ms") is None and item["ms"] < ms:
                        item["end_ms"] = ms
                        break
            continue
        if any(text.startswith(prefix) for prefix in META_PREFIX):
            continue
        if re.match(r"^(作词|作曲|编曲|作詞|編曲)\s*[:：]", text):
            continue
        out.append({"ms": ms, "text": text})
    out.sort(key=lambda item: item["ms"])
    dedup: list[dict[str, Any]] = []
    for item in out:
        if item.get("end_ms") is not None and int(item["end_ms"]) <= item["ms"]:
            item = dict(item)
            item.pop("end_ms", None)
        if dedup and dedup[-1]["text"] == item["text"] and item["ms"] - dedup[-1]["ms"] < 300:
            continue
        dedup.append(item)
    return dedup


def probe_netease_url(song_id: str) -> bool:
    return bool(eapi_play_url(song_id))


def open_netease_audio(song_id: str, timeout: float = 20):
    """Open the eapi CDN URL. None if NetEase has no playable copy."""
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
        try:
            resp.close()
        except Exception:
            pass
        return None
    return resp


def try_netease_download(song_id: str, out_path: Path) -> bool:
    url = eapi_play_url(song_id)
    if not url:
        return False
    cmd = [
        "curl",
        "-sL",
        "-o",
        str(out_path),
        "-w",
        "%{http_code}\n%{url_effective}\n",
        "-A",
        "Mozilla/5.0",
        "-e",
        "https://music.163.com/",
        *curl_proxy_args(),
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    info = result.stdout.strip().splitlines()
    status = info[0] if info else ""
    final_url = info[1] if len(info) > 1 else ""
    if status.startswith("2") and "/404" not in final_url and out_path.exists() and out_path.stat().st_size > 50_000:
        return True
    if out_path.exists():
        out_path.unlink()
    return False


def _list_ytdlp(query: str, ytdlp: str, provider: str, count: int = 15, timeout: float = 60) -> list[dict[str, Any]]:
    prefix = {"soundcloud": f"scsearch{count}:", "youtube": f"ytsearch{count}:"}[provider]
    cmd = [
        ytdlp,
        f"{prefix}{query}",
        "--no-playlist",
        "--flat-playlist",
        "--print",
        "%(webpage_url)s\t%(duration)s\t%(title)s",
        "--quiet",
        "--no-warnings",
        *ytdlp_proxy_args(),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    out: list[dict[str, Any]] = []
    for line in (result.stdout or "").strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        url, dur, title = parts
        try:
            duration = float(dur) if dur and dur != "NA" else None
        except ValueError:
            duration = None
        out.append({"url": url, "duration": duration, "title": title})
    return out


def _pick_best_match(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    for cand in candidates:
        if is_clean_title(str(cand.get("title") or "")):
            return cand
    return None


def _ytdlp_download(page_url: str, out_path: Path) -> bool:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not page_url:
        return False
    tmp_tpl = str(out_path.with_suffix(".%(ext)s"))
    cmd = [
        ytdlp,
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        tmp_tpl,
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--force-overwrites",
        *ytdlp_proxy_args(),
        page_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired:
        return False
    if result.returncode != 0:
        return False
    if out_path.exists() and out_path.stat().st_size > 50_000:
        return True
    for ext in (".m4a", ".opus", ".webm"):
        alt = out_path.with_suffix(ext)
        if alt.exists():
            alt.rename(out_path)
            return True
    return False


def try_ytdlp_search(query: str, out_path: Path, provider: str) -> tuple[bool, str]:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return False, ""
    best = _pick_best_match(_list_ytdlp(query, ytdlp, provider))
    if best is None:
        return False, ""
    return _ytdlp_download(str(best["url"]), out_path), str(best.get("title") or "")


_AUDIO_CACHE: dict[str, dict[str, Any]] = {}


def remember_audio_source(song_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if song_id:
        _AUDIO_CACHE[str(song_id)] = payload
    return payload


def forget_audio_source(song_id: str) -> None:
    _AUDIO_CACHE.pop(str(song_id) or "", None)


def peek_audio_source(song_id: str) -> dict[str, Any]:
    return dict(_AUDIO_CACHE.get(str(song_id) or "") or {})


def _ytdlp_direct_url(page_url: str) -> str:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not page_url:
        return ""
    cmd = [
        ytdlp,
        "-f",
        "bestaudio/best",
        "--get-url",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        *ytdlp_proxy_args(),
        page_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    line = (result.stdout or "").strip().splitlines()
    return line[0] if line and result.returncode == 0 else ""


def _resolve_ytdlp_source(
    song_id: str,
    title: str = "",
    artist: str = "",
    providers: tuple[str, ...] = ("soundcloud", "youtube"),
) -> dict[str, Any]:
    query = " ".join(part for part in (title, artist) if part).strip()
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not query:
        return {}
    for provider in providers:
        best = _pick_best_match(_list_ytdlp(query, ytdlp, provider, count=8))
        if not best:
            continue
        page = str(best["url"] or "")
        if not page or not _ytdlp_direct_url(page):
            continue
        return remember_audio_source(
            song_id,
            {
                "kind": "ytdlp",
                "page": page,
                "title": str(best.get("title") or title),
                "provider": provider,
            },
        )
    return {}


def _resolve_netease_source(song_id: str, title: str = "") -> dict[str, Any]:
    if song_id and probe_netease_url(song_id):
        return remember_audio_source(song_id, {"kind": "netease", "id": song_id, "title": title})
    return {}


def pick_bilibili_mv(title: str, artist: str = "") -> dict[str, Any] | None:
    return bilibili.pick_mv(title, artist)


def try_bilibili_download(bvid: str, mp3_path: Path, video_path: Path | None = None) -> bool:
    return bilibili.download_mv(bvid, mp3_path, video_path)


def open_bilibili_audio(bvid: str, timeout: float = 20):
    return bilibili.open_audio(bvid, timeout=timeout)


def _resolve_bilibili_source(song_id: str, title: str = "", artist: str = "") -> dict[str, Any]:
    hit = pick_bilibili_mv(title, artist)
    if not hit:
        cleaned = clean_search_title(title)
        if cleaned and cleaned != title:
            hit = pick_bilibili_mv(cleaned, "")
    if not hit:
        return {}
    urls = bilibili.play_urls(str(hit.get("bvid") or ""))
    if not urls.get("audio_url"):
        return {}
    return remember_audio_source(
        song_id,
        {
            "kind": "bilibili",
            "bvid": hit["bvid"],
            "title": str(hit.get("title") or title),
            "cover": str(hit.get("pic") or urls.get("cover") or ""),
        },
    )


def is_preview_id(song_id: str) -> bool:
    value = str(song_id or "").strip()
    if not value:
        return False
    if is_mugen_kid(value) or bilibili.is_bvid(value) or value.isdigit():
        return True
    return bool(peek_audio_source(value).get("kind"))


def resolve_audio_source(song_id: str, title: str = "", artist: str = "") -> dict[str, Any]:
    """Mugen is handled by the caller. Then Bilibili → SoundCloud → NetEase → YouTube."""
    if bilibili.is_bvid(song_id):
        cached = peek_audio_source(song_id)
        if cached.get("kind") == "bilibili":
            return cached
        urls = bilibili.play_urls(song_id)
        if not urls.get("audio_url"):
            return {}
        return remember_audio_source(
            song_id,
            {
                "kind": "bilibili",
                "bvid": song_id,
                "title": str(urls.get("title") or title),
                "cover": str(urls.get("cover") or ""),
            },
        )
    cached = peek_audio_source(song_id)
    if cached.get("kind") == "bilibili":
        return cached
    if cached.get("kind") == "ytdlp" and not str(song_id).isdigit():
        return cached
    if not str(song_id).isdigit():
        return cached if cached.get("kind") else {}
    netease = _resolve_netease_source(song_id, title)
    if netease:
        return netease
    bili = _resolve_bilibili_source(song_id, title, artist)
    if bili:
        return bili
    if cached.get("kind") in {"netease", "ytdlp"}:
        return cached
    return (
        _resolve_ytdlp_source(song_id, title, artist, ("soundcloud",))
        or _resolve_ytdlp_source(song_id, title, artist, ("youtube",))
    )


def _open_ytdlp_stream(page: str):
    direct = _ytdlp_direct_url(page)
    if not direct:
        return None
    req = urllib.request.Request(direct, headers={"User-Agent": BROWSER_UA})
    try:
        return urlopen(req, timeout=30, via_proxy=True)
    except Exception:
        return None


def open_preview_stream(song_id: str, title: str = "", artist: str = "", media: str = ""):
    if is_mugen_kid(song_id):
        resp = open_mugen_preview(song_id, media_name=media)
        return resp, {"kind": "mugen", "title": title}
    source = resolve_audio_source(song_id, title, artist)
    if source.get("kind") == "bilibili":
        resp = open_bilibili_audio(str(source.get("bvid") or ""))
        if resp is not None:
            return resp, source
        forget_audio_source(song_id)
        source = (
            _resolve_ytdlp_source(song_id, title, artist, ("soundcloud",))
            or _resolve_netease_source(song_id, title)
            or _resolve_ytdlp_source(song_id, title, artist, ("youtube",))
        )
    if source.get("kind") == "ytdlp" and source.get("provider") == "soundcloud":
        resp = _open_ytdlp_stream(str(source.get("page") or ""))
        if resp is not None:
            return resp, source
        forget_audio_source(song_id)
        source = _resolve_netease_source(song_id, title) or _resolve_ytdlp_source(
            song_id, title, artist, ("youtube",)
        )
    if source.get("kind") == "netease":
        resp = open_netease_audio(song_id)
        if resp is not None:
            return resp, source
        forget_audio_source(song_id)
        source = _resolve_ytdlp_source(song_id, title, artist, ("youtube",))
    if source.get("kind") == "ytdlp":
        resp = _open_ytdlp_stream(str(source.get("page") or ""))
        if resp is not None:
            return resp, source
        forget_audio_source(song_id)
        return None, source
    return None, source


def import_song(
    *,
    query: str,
    out_dir: Path,
    song_id: str | None = None,
    prefer_ytdlp: bool = False,
) -> dict[str, Any]:
    """Search (or use pinned id), write lyrics.lrc + original.mp3 + skeleton.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if song_id and is_mugen_kid(song_id):
        return import_mugen_song(song_id, out_dir, query=query)
    if not song_id:
        chosen = pick_vocal_hit(search_mugen(query, count=8).get("hits") or [])
        if chosen and chosen.get("id"):
            return import_mugen_song(str(chosen["id"]), out_dir, query=query)
    results = search_tonzhon(query)
    chosen: dict[str, Any] | None = None
    if song_id:
        chosen = next((item for item in results if str(item.get("id")) == str(song_id)), None)
        if chosen is None:
            chosen = {"id": song_id, "name": query, "artist": [], "album": [], "pic": ""}
    elif not results:
        raise RuntimeError(f"tonzhon 没有搜到：{query}")
    else:
        chosen = results[0]
        for item in results:
            if is_clean_title(str(item.get("name") or "")):
                chosen = item
                break

    title_name = str(chosen.get("name") or query)
    artist_name = flatten_artists(chosen)
    kugou = fetch_kugou_lyrics(title_name, artist_name)
    lyric_source = "netease"
    needs_align = True
    language = ""
    if kugou and kugou.get("timeline"):
        from lovktv.pipeline.lyrics import write_subtitles

        timeline = kugou["timeline"]
        write_subtitles(timeline, out_dir)
        (out_dir / "lyrics.lrc").write_text(str(kugou.get("lrc") or ""), encoding="utf-8")
        lines = [
            {"ms": int(cue["start_ms"]), "text": str(cue.get("text") or "")}
            for cue in timeline.get("cues") or []
        ]
        lyric_source = "kugou"
        needs_align = False
        language = str(timeline.get("language") or "")
    else:
        lyric_id = str(chosen.get("id") or "")
        lrc = fetch_lyric(lyric_id) if lyric_id.isdigit() else ""
        if not lrc.strip():
            for song in _tonzhon_hits(title_name, 5, 1):
                sid = str(song.get("id") or "")
                if not sid.isdigit():
                    continue
                try:
                    lrc = fetch_lyric(sid)
                except Exception:
                    lrc = ""
                if lrc.strip():
                    break
        if not lrc.strip():
            raise RuntimeError("歌词为空")
        (out_dir / "lyrics.lrc").write_text(lrc, encoding="utf-8")
        lines = parse_lrc(lrc)
    if not lines:
        raise RuntimeError("歌词为空")

    audio_file = None
    audio_source = "none"
    audio_title = ""
    audio_bvid = ""
    has_video = False
    mp3_path = out_dir / "original.mp3"
    mtv_path = out_dir / "mtv.mp4"
    chosen_id = str(chosen.get("id") or "")
    pic = str(chosen.get("pic") or "")
    cached = peek_audio_source(chosen_id)
    pinned_bvid = str(cached.get("bvid") or (chosen_id if bilibili.is_bvid(chosen_id) else "") or (song_id if bilibili.is_bvid(song_id or "") else ""))
    if audio_file is None and pinned_bvid:
        if try_bilibili_download(pinned_bvid, mp3_path, mtv_path):
            audio_file = "original.mp3"
            audio_source = "bilibili"
            audio_title = str(cached.get("title") or title_name)
            audio_bvid = pinned_bvid
            has_video = mtv_path.exists()
            if not pic and cached.get("cover"):
                pic = str(cached["cover"])
    if audio_file is None and cached.get("page"):
        if _ytdlp_download(str(cached["page"]), mp3_path):
            audio_file = "original.mp3"
            audio_source = str(cached.get("provider") or "ytdlp")
            audio_title = str(cached.get("title") or "")
    ytdlp_query = f"{chosen.get('name') or ''} {flatten_artists(chosen)}".strip() or query
    if audio_file is None:
        hit = pick_bilibili_mv(title_name, artist_name) or pick_bilibili_mv(clean_search_title(title_name), "")
        if hit and try_bilibili_download(str(hit["bvid"]), mp3_path, mtv_path):
            audio_file = "original.mp3"
            audio_source = "bilibili"
            audio_title = str(hit.get("title") or "")
            audio_bvid = str(hit["bvid"])
            has_video = mtv_path.exists()
            if not pic and hit.get("pic"):
                pic = str(hit["pic"])
    if audio_file is None:
        ok, got_title = try_ytdlp_search(ytdlp_query, mp3_path, "soundcloud")
        if ok:
            audio_file = "original.mp3"
            audio_source = "soundcloud"
            audio_title = got_title
    if audio_file is None and not prefer_ytdlp and try_netease_download(chosen_id, mp3_path):
        audio_file = "original.mp3"
        audio_source = "netease"
    if audio_file is None:
        ok, got_title = try_ytdlp_search(ytdlp_query, mp3_path, "youtube")
        if ok:
            audio_file = "original.mp3"
            audio_source = "youtube"
            audio_title = got_title

    if has_video:
        lyrics_path = out_dir / "lyrics.json"
        if lyrics_path.exists():
            try:
                timeline = json.loads(lyrics_path.read_text(encoding="utf-8"))
                if isinstance(timeline, dict):
                    timeline["native_video"] = True
                    lyrics_path.write_text(
                        json.dumps(timeline, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except (OSError, json.JSONDecodeError):
                pass

    cover_file = ""
    if pic.startswith("http"):
        cover_path = out_dir / "cover.jpg"
        try:
            req = urllib.request.Request(pic, headers={"User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if len(data) > 2000:
                cover_path.write_bytes(data)
                cover_file = "cover.jpg"
        except Exception:
            cover_file = ""

    title = f"{chosen.get('name')} · {flatten_artists(chosen)}"
    skeleton = {
        "title": title,
        "artist": artist_name,
        "language": language,
        "needs_align": needs_align,
        "source": {
            "provider": "tonzhon.com / netease",
            "netease_id": str(chosen.get("id")),
            "query": query,
            "lyrics": lyric_source,
            "kugou_id": str((kugou or {}).get("candidate", {}).get("id") or ""),
            "bvid": audio_bvid,
        },
        "audio": {"file": audio_file, "source": audio_source, "title": audio_title},
        "cover": cover_file,
        "has_video": has_video,
        "sentences": [
            {
                "id": f"s{index}",
                "timestamp_ms": line["ms"],
                "raw": line["text"],
            }
            for index, line in enumerate(lines, 1)
        ],
    }
    (out_dir / "skeleton.json").write_text(
        json.dumps(skeleton, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return skeleton
