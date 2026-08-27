"""Song search + download, following vendor/lovjpn/scripts/fetch_song.py.

tonzhon.com search/lyric → NetEase outer URL → yt-dlp SoundCloud → YouTube.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from lovktv.catalog.kugou import fetch_kugou_lyrics
from lovktv.catalog.mugen import import_mugen_song, is_mugen_kid, open_mugen_preview, pick_vocal_hit, search_mugen

TONZHON_API = "https://tonzhon.com/api.php"
NETEASE_OUTER = "https://music.163.com/song/media/outer/url?id={id}.mp3"
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


def is_clean_title(title: str) -> bool:
    low = (title or "").lower()
    return not any(tok in low for tok in BAD_TITLE_TOKENS)


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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def search_songs(query: str, count: int = 10, page: int = 1) -> dict[str, Any]:
    page = max(1, int(page))
    count = max(1, min(int(count), 30))
    mugen = search_mugen(query, count=count, page=page)
    hits = list(mugen.get("hits") or [])
    used_netease = False
    netease_full = False
    if len(hits) < count:
        tonzhon = search_tonzhon(query, count=count, page=page)
        used_netease = True
        netease_full = len(tonzhon) >= count
        for song in tonzhon:
            title = str(song.get("name") or "")
            song_id = str(song.get("id") or "")
            hits.append(
                {
                    "id": song_id,
                    "title": title,
                    "artist": flatten_artists(song),
                    "album": (song.get("album") or [""])[0] if isinstance(song.get("album"), list) else song.get("album") or "",
                    "pic": song.get("pic") or "",
                    "source": "netease",
                    "clean": is_clean_title(title),
                    "preview_url": f"/api/preview/{song_id}" if song_id else "",
                }
            )
            if len(hits) >= count:
                break
    return {
        "query": query,
        "page": page,
        "count": count,
        "has_more": bool(mugen.get("has_more")) or (used_netease and netease_full),
        "hits": hits[:count],
        "sources": ["mugen", "netease"],
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
    url = NETEASE_OUTER.format(id=song_id)
    cmd = ["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code}\n%{redirect_url}\n", "--max-redirs", "0", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    info = (result.stdout or "").strip().splitlines()
    status = info[0] if info else ""
    redirect = info[1] if len(info) > 1 else ""
    return status.startswith("3") and "/404" not in redirect


def open_netease_audio(song_id: str, timeout: float = 20):
    """Follow the NetEase outer URL. None if it is a 404/HTML stub."""
    url = NETEASE_OUTER.format(id=song_id)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": BROWSER_UA, "Referer": "https://music.163.com/"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
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
    url = NETEASE_OUTER.format(id=song_id)
    cmd = ["curl", "-sL", "-o", str(out_path), "-w", "%{http_code}\n%{url_effective}\n", url]
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


def _list_ytdlp(query: str, ytdlp: str, provider: str, count: int = 15) -> list[dict[str, Any]]:
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
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
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


def peek_audio_source(song_id: str) -> dict[str, Any]:
    return dict(_AUDIO_CACHE.get(str(song_id) or "") or {})


def _ytdlp_direct_url(page_url: str) -> str:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not page_url:
        return ""
    cmd = [ytdlp, "-f", "bestaudio/best", "--get-url", "--no-playlist", "--quiet", "--no-warnings", page_url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    line = (result.stdout or "").strip().splitlines()
    return line[0] if line and result.returncode == 0 else ""


def resolve_audio_source(song_id: str, title: str = "", artist: str = "") -> dict[str, Any]:
    """Pick the same audio the user will import: NetEase, else a cached yt-dlp page."""
    cached = peek_audio_source(song_id)
    if cached.get("kind") in {"netease", "ytdlp"}:
        return cached
    if song_id and probe_netease_url(song_id):
        return remember_audio_source(song_id, {"kind": "netease", "id": song_id, "title": title})
    query = " ".join(part for part in (title, artist) if part).strip()
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not query:
        return {}
    for provider in ("youtube", "soundcloud"):
        best = _pick_best_match(_list_ytdlp(query, ytdlp, provider, count=8))
        if not best:
            continue
        return remember_audio_source(
            song_id,
            {
                "kind": "ytdlp",
                "page": best["url"],
                "title": str(best.get("title") or title),
                "provider": provider,
            },
        )
    return {}


def open_preview_stream(song_id: str, title: str = "", artist: str = "", media: str = ""):
    if is_mugen_kid(song_id):
        resp = open_mugen_preview(song_id, media_name=media)
        return resp, {"kind": "mugen", "title": title}
    source = resolve_audio_source(song_id, title, artist)
    if source.get("kind") == "netease":
        return open_netease_audio(song_id), source
    page = str(source.get("page") or "")
    if not page:
        return None, source
    direct = _ytdlp_direct_url(page)
    if not direct:
        return None, source
    req = urllib.request.Request(direct, headers={"User-Agent": BROWSER_UA})
    try:
        return urllib.request.urlopen(req, timeout=30), source
    except Exception:
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
        if not prefer_ytdlp:
            for item in results:
                item_id = str(item.get("id") or "")
                if item_id and is_clean_title(str(item.get("name") or "")) and probe_netease_url(item_id):
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
        lrc = fetch_lyric(str(chosen.get("id")))
        if not lrc.strip():
            raise RuntimeError("歌词为空")
        (out_dir / "lyrics.lrc").write_text(lrc, encoding="utf-8")
        lines = parse_lrc(lrc)
    if not lines:
        raise RuntimeError("歌词为空")

    audio_file = None
    audio_source = "none"
    audio_title = ""
    mp3_path = out_dir / "original.mp3"
    chosen_id = str(chosen.get("id") or "")
    cached = peek_audio_source(chosen_id)
    if not prefer_ytdlp and try_netease_download(chosen_id, mp3_path):
        audio_file = "original.mp3"
        audio_source = "netease"
    if audio_file is None and cached.get("page"):
        if _ytdlp_download(str(cached["page"]), mp3_path):
            audio_file = "original.mp3"
            audio_source = str(cached.get("provider") or "ytdlp")
            audio_title = str(cached.get("title") or "")
    if audio_file is None:
        ytdlp_query = f"{chosen.get('name') or ''} {flatten_artists(chosen)}".strip() or query
        for provider in ("soundcloud", "youtube"):
            ok, got_title = try_ytdlp_search(ytdlp_query, mp3_path, provider)
            if ok:
                audio_file = "original.mp3"
                audio_source = provider
                audio_title = got_title
                break

    cover_file = ""
    pic = str(chosen.get("pic") or "")
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
        },
        "audio": {"file": audio_file, "source": audio_source, "title": audio_title},
        "cover": cover_file,
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
