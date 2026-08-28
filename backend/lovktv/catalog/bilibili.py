"""Bilibili official MV via public web APIs.

yt-dlp's webpage extractor often gets HTTP 412 from datacenter IPs.
`api.bilibili.com` search / view / dash playurl still return without
cookies. CDN segments need Referer `https://www.bilibili.com/`.
Stay off Clash; these hosts are China CDN.
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

from lovktv.catalog.http import urlopen

SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL = "https://api.bilibili.com/x/player/playurl"
PAGE_ORIGIN = "https://www.bilibili.com"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HTML_TAG = re.compile(r"<[^>]+>")
MIN_SEC = 90
MAX_SEC = 480
SKIP_TITLE = (
    "合集",
    "串烧",
    "連播",
    "连播",
    "全集",
    "歌单",
    "playlist",
    "medley",
    "remix",
    "cover",
    "翻唱",
    "karaoke",
    "伴奏",
    "off vocal",
    "歌ってみた",
)


def headers(referer: str = PAGE_ORIGIN + "/") -> dict[str, str]:
    return {
        "User-Agent": BROWSER_UA,
        "Referer": referer,
        "Origin": PAGE_ORIGIN,
    }


SEARCH_REFERER = "https://search.bilibili.com/"


def api_get(url: str, timeout: float = 12) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers())
    with urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def strip_title(text: str) -> str:
    return HTML_TAG.sub("", text or "").replace("&nbsp;", " ").strip()


def parse_duration(value: Any) -> int | None:
    if value is None or value == "" or value == "NA":
        return None
    if isinstance(value, (int, float)):
        secs = int(value)
        return secs if secs > 0 else None
    text = str(value).strip()
    if text.isdigit():
        secs = int(text)
        return secs if secs > 0 else None
    parts = text.split(":")
    if not 2 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None
    nums = [int(part) for part in parts]
    if len(nums) == 2:
        secs = nums[0] * 60 + nums[1]
    else:
        secs = nums[0] * 3600 + nums[1] * 60 + nums[2]
    return secs if secs > 0 else None


def cover_url(pic: str) -> str:
    pic = str(pic or "").strip()
    if pic.startswith("//"):
        return "https:" + pic
    return pic


def search_videos(query: str, count: int = 20) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    url = SEARCH_URL + "?" + urllib.parse.urlencode(
        {
            "search_type": "video",
            "keyword": query,
            "page": 1,
            "page_size": max(1, min(int(count), 30)),
        }
    )
    raw: list[Any] = []
    for _attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers(SEARCH_REFERER))
            with urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict) or int(payload.get("code") or 0) != 0:
            continue
        result = (payload.get("data") or {}).get("result") or []
        if isinstance(result, list) and result:
            raw = result
            break
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        bvid = str(item.get("bvid") or "").strip()
        title = strip_title(str(item.get("title") or ""))
        if not bvid or not title:
            continue
        out.append(
            {
                "bvid": bvid,
                "title": title,
                "author": str(item.get("author") or ""),
                "typename": str(item.get("typename") or ""),
                "duration": parse_duration(item.get("duration")),
                "pic": cover_url(str(item.get("pic") or "")),
                "page": f"{PAGE_ORIGIN}/video/{bvid}",
            }
        )
    return out


def score_hit(hit: dict[str, Any], title: str, artist: str = "") -> int:
    video_title = str(hit.get("title") or "")
    low = video_title.lower()
    if any(tok in low for tok in SKIP_TITLE):
        return -1
    duration = hit.get("duration")
    if isinstance(duration, int) and not (MIN_SEC <= duration <= MAX_SEC):
        return -1
    if title and title.casefold() not in video_title.casefold():
        return -1
    author = str(hit.get("author") or "")
    if artist and artist.casefold() not in video_title.casefold() and artist.casefold() not in author.casefold():
        return -1
    typename = str(hit.get("typename") or "")
    score = 0
    if "MV" in typename.upper() or typename.upper() == "MV":
        score += 100
    if "正版" in video_title:
        score += 80
    if "官方" in video_title:
        score += 50
    if "mv" in low or "MV" in video_title:
        score += 40
    if artist:
        score += 20
    if isinstance(duration, int):
        score += max(0, 24 - abs(duration - 240) // 15)
    return score


def pick_mv(title: str, artist: str = "") -> dict[str, Any] | None:
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return None
    queries = []
    base = " ".join(part for part in (title, artist) if part)
    queries.append(f"{base} MV")
    if base not in queries:
        queries.append(base)
    seen: set[str] = set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for query in queries:
        for hit in search_videos(query):
            bvid = hit["bvid"]
            if bvid in seen:
                continue
            seen.add(bvid)
            points = score_hit(hit, title, artist)
            if points >= 0:
                ranked.append((points, hit))
        if any(points >= 120 for points, _ in ranked):
            break
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _dash_url(item: dict[str, Any]) -> str:
    return str(
        item.get("baseUrl")
        or item.get("base_url")
        or ((item.get("backupUrl") or item.get("backup_url") or [None])[0])
        or ""
    )


def _pick_audio(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [item for item in items if isinstance(item, dict) and _dash_url(item)]
    if not usable:
        return None
    usable.sort(key=lambda item: int(item.get("bandwidth") or 0), reverse=True)
    return usable[0]


def _pick_video(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [item for item in items if isinstance(item, dict) and _dash_url(item)]
    if not usable:
        return None

    def key(item: dict[str, Any]) -> tuple[int, int, int]:
        height = int(item.get("height") or 0)
        bandwidth = int(item.get("bandwidth") or 0)
        over = 0 if height and height <= 720 else 1
        return (over, abs((height or 720) - 720), bandwidth)

    usable.sort(key=key)
    return usable[0]


def play_urls(bvid: str, timeout: float = 12) -> dict[str, str]:
    bvid = str(bvid or "").strip()
    if not bvid:
        return {}
    try:
        view = api_get(f"{VIEW_URL}?{urllib.parse.urlencode({'bvid': bvid})}", timeout=timeout)
    except Exception:
        return {}
    data = view.get("data") if int(view.get("code") or 0) == 0 else None
    if not isinstance(data, dict):
        return {}
    cid = data.get("cid")
    if not cid:
        return {}
    query = urllib.parse.urlencode(
        {"bvid": bvid, "cid": cid, "qn": 64, "fnval": 16, "fourk": 0}
    )
    try:
        play = api_get(f"{PLAYURL}?{query}", timeout=timeout)
    except Exception:
        return {}
    dash = ((play.get("data") or {}).get("dash") or {}) if int(play.get("code") or 0) == 0 else {}
    audio = _pick_audio(dash.get("audio") or [])
    video = _pick_video(dash.get("video") or [])
    audio_url = _dash_url(audio) if audio else ""
    if not audio_url:
        return {}
    return {
        "audio_url": audio_url,
        "video_url": _dash_url(video) if video else "",
        "title": str(data.get("title") or ""),
        "cover": cover_url(str(data.get("pic") or "")),
    }


def media_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers=headers())


def open_audio(bvid: str, timeout: float = 20):
    urls = play_urls(bvid)
    audio_url = urls.get("audio_url") or ""
    if not audio_url:
        return None
    try:
        return urlopen(media_request(audio_url), timeout=timeout)
    except Exception:
        return None


def _curl_download(url: str, dest: Path, timeout: int = 180) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl",
        "-sL",
        "-o",
        str(dest),
        "-w",
        "%{http_code}",
        "-A",
        BROWSER_UA,
        "-e",
        PAGE_ORIGIN + "/",
        "--max-time",
        str(timeout),
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    ok = (result.stdout or "").strip().startswith("2") and dest.exists() and dest.stat().st_size > 20_000
    if not ok and dest.exists():
        dest.unlink()
    return ok


def _ffmpeg(*args: str, timeout: int = 300) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        subprocess.run(["ffmpeg", "-y", *args], check=True, timeout=timeout, capture_output=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def _to_mp3(src: Path, dest: Path) -> bool:
    if not _ffmpeg("-i", str(src), "-c:a", "libmp3lame", "-q:a", "2", str(dest)):
        return False
    return dest.exists() and dest.stat().st_size > 50_000


def _to_mtv(src: Path, dest: Path) -> bool:
    if _ffmpeg(
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-an",
        "-movflags",
        "+faststart",
        str(dest),
    ) and dest.exists() and dest.stat().st_size > 1000:
        return True
    if dest.exists():
        dest.unlink()
    if _ffmpeg(
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-an",
        "-movflags",
        "+faststart",
        str(dest),
        timeout=600,
    ) and dest.exists() and dest.stat().st_size > 1000:
        return True
    if dest.exists():
        dest.unlink()
    return False


def download_mv(bvid: str, mp3_path: Path, video_path: Path | None = None) -> bool:
    urls = play_urls(bvid)
    audio_url = urls.get("audio_url") or ""
    if not audio_url:
        return False
    audio_tmp = mp3_path.with_suffix(".bili.m4s")
    try:
        if not _curl_download(audio_url, audio_tmp):
            return False
        if not _to_mp3(audio_tmp, mp3_path):
            return False
        video_url = (urls.get("video_url") or "") if video_path is not None else ""
        if video_url and video_path is not None:
            video_tmp = video_path.with_suffix(".bili.m4s")
            try:
                if _curl_download(video_url, video_tmp, timeout=300):
                    _to_mtv(video_tmp, video_path)
            finally:
                if video_tmp.exists():
                    video_tmp.unlink()
        return True
    finally:
        if audio_tmp.exists():
            audio_tmp.unlink()
