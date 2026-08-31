"""Search providers and result normalization for the catalog."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from lovktv.catalog import bilibili
from lovktv.catalog.http import urlopen, ytdlp_proxy_args
from lovktv.catalog.mugen import search_mugen

TONZHON_API = "https://tonzhon.com/api.php"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
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
SEARCH_CHANNELS = ("mugen", "bilibili", "soundcloud")


def annotate_duration_match(hit: dict[str, Any]) -> dict[str, Any]:
    """Attach a comparable lyric/audio duration score when metadata permits.

    Mugen's timed ASS is shipped with the same media, so a ready lyric hit is
    an exact match by construction. Other providers may populate both fields
    later (for example from a lyric cache); unknown durations remain neutral.
    """
    def coerce_duration(value: Any, *, seconds: bool) -> int | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        return int(round(number * 1000)) if seconds else int(round(number))

    song_ms = hit.get("duration_ms")
    if song_ms is None:
        song_ms = coerce_duration(hit.get("duration"), seconds=True)
        if song_ms is not None:
            hit["duration_ms"] = song_ms
    else:
        song_ms = coerce_duration(song_ms, seconds=False)
        if song_ms is not None:
            hit["duration_ms"] = song_ms
    lyric_ms = hit.get("lyrics_duration_ms")
    if lyric_ms is None:
        lyric_ms = coerce_duration(hit.get("lyrics_duration"), seconds=True)
        if lyric_ms is not None:
            hit["lyrics_duration_ms"] = lyric_ms
    else:
        lyric_ms = coerce_duration(lyric_ms, seconds=False)
        if lyric_ms is not None:
            hit["lyrics_duration_ms"] = lyric_ms
    if (
        hit.get("source") == "mugen"
        and hit.get("lyrics_ready")
        and isinstance(song_ms, int)
        and song_ms > 0
    ):
        lyric_ms = song_ms
        hit["lyrics_duration_ms"] = song_ms
    if song_ms is None or lyric_ms is None:
        hit.setdefault("duration_match", "unknown")
        hit.setdefault("duration_match_score", 0)
        # Keep the public field explicit even when a provider does not expose
        # both durations.  ``available`` means lyrics are present but cannot
        # be compared to the audio length yet; ``unknown`` means the provider
        # did not tell us whether lyrics exist.
        if hit.get("lyrics_ready") is True:
            hit.setdefault("lyrics_match", "available")
        elif hit.get("lyrics_ready") is False:
            hit.setdefault("lyrics_match", "none")
        else:
            hit.setdefault("lyrics_match", "unknown")
        hit.setdefault("lyrics_match_score", None)
        return hit
    diff = abs(song_ms - lyric_ms)
    ratio = diff / max(song_ms, lyric_ms)
    hit["duration_diff_ms"] = diff
    hit["duration_match"] = "exact" if diff <= 1500 else ("close" if ratio <= 0.08 else "mismatch")
    hit["duration_match_score"] = 3 if diff <= 1500 else (2 if ratio <= 0.03 else (1 if ratio <= 0.08 else -1))
    # A human-readable score for the search card.  Clamp to zero so a very
    # different lyric track is never presented as a negative percentage.
    hit["lyrics_match"] = hit["duration_match"]
    hit["lyrics_match_score"] = (
        100
        if hit["duration_match"] == "exact"
        else max(0, min(100, int(round((1 - ratio) * 100))))
    )
    return hit


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


def search_tonzhon(
    query: str, count: int = 12, source: str = "netease", page: int = 1
) -> list[dict[str, Any]]:
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
    return data if isinstance(data, list) else []


def flatten_artists(song: dict[str, Any]) -> str:
    artists = song.get("artist") or []
    names: list[str] = []
    for item in artists:
        if isinstance(item, list):
            names.extend(str(part) for part in item if part)
        elif item:
            names.append(str(item))
    return " / ".join(names)


def search_bilibili_hits(
    query: str, count: int = 8, page: int = 1
) -> list[dict[str, Any]]:
    try:
        videos = bilibili.search_videos(query, count=max(count, 12), page=page)
    except Exception:
        return []
    hits: list[dict[str, Any]] = []
    for item in videos:
        title, bvid = str(item.get("title") or ""), str(item.get("bvid") or "")
        if (
            not bvid
            or not title
            or any(tok in title.lower() for tok in bilibili.SKIP_TITLE)
        ):
            continue
        duration = item.get("duration")
        if isinstance(duration, int) and not (
            bilibili.MIN_SEC <= duration <= bilibili.MAX_SEC
        ):
            continue
        from .audio import remember_audio_source

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
            annotate_duration_match({
                "id": bvid,
                "title": title,
                "artist": str(item.get("author") or ""),
                "album": "",
                "pic": str(item.get("pic") or ""),
                "source": "bilibili",
                "is_mv": True,
                "clean": is_clean_title(title),
                "preview_url": f"/api/preview/{bvid}",
                "duration": duration,
            })
        )
        if len(hits) >= count:
            break
    return hits


def _list_ytdlp(
    query: str, ytdlp: str, provider: str, count: int = 15, timeout: float = 60
) -> list[dict[str, Any]]:
    prefix = {"soundcloud": f"scsearch{count}:", "youtube": f"ytsearch{count}:"}[
        provider
    ]
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
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
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


def search_ytdlp_hits(
    query: str, provider: str, count: int = 5, page: int = 1
) -> list[dict[str, Any]]:
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
        title, page_url = str(row.get("title") or ""), str(row.get("url") or "")
        if not page_url:
            continue
        hid = f"{provider}_{hashlib.sha1(page_url.encode('utf-8')).hexdigest()[:12]}"
        from .audio import remember_audio_source

        remember_audio_source(
            hid,
            {"kind": "ytdlp", "page": page_url, "title": title, "provider": provider},
        )
        hits.append(
            annotate_duration_match({
                "id": hid,
                "title": title,
                "artist": "",
                "album": "",
                "pic": "",
                "source": provider,
                "is_mv": provider == "youtube",
                "clean": is_clean_title(title),
                "preview_url": f"/api/preview/{hid}",
                "duration": row.get("duration"),
            })
        )
        if len(hits) >= count:
            break
    return hits


def merge_channel_hits(
    groups: dict[str, list[dict[str, Any]]], count: int
) -> list[dict[str, Any]]:
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
    page, count = max(1, int(page)), max(1, min(int(count), 30))
    extra = min(count, 5)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [
            pool.submit(search_mugen, query, count, page),
            pool.submit(search_bilibili_hits, query, count, page),
            pool.submit(search_ytdlp_hits, query, "soundcloud", extra, page),
        ]
        try:
            mugen = jobs[0].result()
        except Exception:
            mugen = {"hits": [], "has_more": False}
        try:
            bili = jobs[1].result()
        except Exception:
            bili = []
        try:
            soundcloud = jobs[2].result()
        except Exception:
            soundcloud = []
    groups = {
        "mugen": list(mugen.get("hits") or []),
        "bilibili": bili,
        "soundcloud": soundcloud,
    }
    # Collect every hit returned by the providers before ranking.  Taking the
    # first ``count`` items from the round-robin merge would hide a later
    # exact-duration match behind a full page of unknown-duration results.
    hits = merge_channel_hits(groups, sum(len(bucket) for bucket in groups.values()))
    hits = [annotate_duration_match(hit) for hit in hits]
    hits.sort(
        # Python's sort is stable, so the round-robin provider order remains
        # the tie-breaker while duration quality is the primary ranking.
        key=lambda hit: int(hit.get("duration_match_score") or 0),
        reverse=True,
    )
    hits = hits[:count]
    available = sum(len(bucket) for bucket in groups.values())
    return {
        "query": query,
        "page": page,
        "count": count,
        "has_more": bool(mugen.get("has_more"))
        or available > len(hits)
        or any(len(groups[key]) >= count for key in SEARCH_CHANNELS),
        "hits": hits,
        "sources": list(SEARCH_CHANNELS),
    }
