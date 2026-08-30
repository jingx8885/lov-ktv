"""Audio source cache and provider adapters."""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from lovktv.catalog import bilibili
from lovktv.catalog.http import curl_proxy_args, urlopen, ytdlp_proxy_args
from lovktv.catalog.netease import eapi_play_url, media_request

from .search import BROWSER_UA, _list_ytdlp, clean_search_title, is_clean_title

_AUDIO_CACHE: dict[str, dict[str, Any]] = {}


def remember_audio_source(song_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if song_id:
        _AUDIO_CACHE[str(song_id)] = payload
    return payload


def forget_audio_source(song_id: str) -> None:
    _AUDIO_CACHE.pop(str(song_id) or "", None)


def peek_audio_source(song_id: str) -> dict[str, Any]:
    return dict(_AUDIO_CACHE.get(str(song_id) or "") or {})


def probe_netease_url(song_id: str) -> bool:
    return bool(eapi_play_url(song_id))


def open_netease_audio(song_id: str, timeout: float = 20):
    url = eapi_play_url(song_id)
    if not url:
        return None
    try:
        resp = urlopen(media_request(url), timeout=timeout, via_proxy=True)
    except Exception:
        return None
    final, ctype = (
        str(resp.geturl() or ""),
        str(resp.headers.get("Content-Type") or "").lower(),
    )
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
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    info = result.stdout.strip().splitlines()
    status = info[0] if info else ""
    final_url = info[1] if len(info) > 1 else ""
    if (
        status.startswith("2")
        and "/404" not in final_url
        and out_path.exists()
        and out_path.stat().st_size > 50_000
    ):
        return True
    if out_path.exists():
        out_path.unlink()
    return False


def _ytdlp_download(page_url: str, out_path: Path) -> bool:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not page_url:
        return False
    cmd = [
        ytdlp,
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        str(out_path.with_suffix(".%(ext)s")),
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--force-overwrites",
        *ytdlp_proxy_args(),
        page_url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, check=False
        )
    except subprocess.TimeoutExpired:
        return False
    if result.returncode != 0:
        return False
    if out_path.exists() and out_path.stat().st_size > 50_000:
        return True
    for ext in (".m4a", ".opus", ".webm"):
        alt = out_path.with_suffix(ext)
        if alt.exists() and alt.stat().st_size > 50_000:
            alt.rename(out_path)
            return True
    return False


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
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90, check=False
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    line = (result.stdout or "").strip().splitlines()
    return line[0] if line and result.returncode == 0 else ""


def _pick_best_match(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (cand for cand in candidates if is_clean_title(str(cand.get("title") or ""))),
        None,
    )


def try_ytdlp_search(query: str, out_path: Path, provider: str) -> tuple[bool, str]:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return False, ""
    best = _pick_best_match(_list_ytdlp(query, ytdlp, provider))
    if best is None:
        return False, ""
    return _ytdlp_download(str(best["url"]), out_path), str(best.get("title") or "")


def pick_bilibili_mv(title: str, artist: str = "") -> dict[str, Any] | None:
    return bilibili.pick_mv(title, artist)


def try_bilibili_download(
    bvid: str, mp3_path: Path, video_path: Path | None = None
) -> bool:
    return bilibili.download_mv(bvid, mp3_path, video_path)


def sync_video_to_audio(video_path: Path, audio_path: Path) -> bool:
    """Replace video audio and make the video exactly as long as the MP3.

    The MP3 is authoritative: a longer video is trimmed, while a shorter one
    loops seamlessly before being trimmed. The resulting track is encoded
    muted at playback by the client, but carrying the same timeline avoids
    drift for native-MV playback.
    """
    if not video_path.exists() or not audio_path.exists() or not shutil.which("ffmpeg"):
        return False
    try:
        from lovktv.pipeline.audio import probe_duration_ms

        video_ms = probe_duration_ms(video_path)
        audio_ms = probe_duration_ms(audio_path)
    except Exception:
        return False
    if video_ms <= 0 or audio_ms <= 0:
        return False
    tmp = video_path.with_suffix(video_path.suffix + ".sync.part")
    cmd = ["ffmpeg", "-y"]
    if video_ms < audio_ms:
        cmd += ["-stream_loop", "-1"]
    cmd += [
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        f"{audio_ms / 1000:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=900, capture_output=True)
        if not tmp.exists() or tmp.stat().st_size <= 1000:
            return False
        tmp.replace(video_path)
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    finally:
        tmp.unlink(missing_ok=True)


def open_bilibili_audio(bvid: str, timeout: float = 20):
    return bilibili.open_audio(bvid, timeout=timeout)


def _resolve_bilibili_source(
    song_id: str, title: str = "", artist: str = ""
) -> dict[str, Any]:
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


def _resolve_netease_source(song_id: str, title: str = "") -> dict[str, Any]:
    if song_id and probe_netease_url(song_id):
        return remember_audio_source(
            song_id, {"kind": "netease", "id": song_id, "title": title}
        )
    return {}


def _resolve_ytdlp_source(
    song_id: str,
    title: str = "",
    artist: str = "",
    providers: tuple[str, ...] = ("soundcloud", "youtube"),
) -> dict[str, Any]:
    query = " ".join(p for p in (title, artist) if p).strip()
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not query:
        return {}
    for provider in providers:
        best = _pick_best_match(_list_ytdlp(query, ytdlp, provider, count=8))
        if best and (page := str(best.get("url") or "")) and _ytdlp_direct_url(page):
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


def is_preview_id(song_id: str) -> bool:
    value = str(song_id or "").strip()
    from lovktv.catalog.mugen import is_mugen_kid

    return bool(value) and (
        is_mugen_kid(value)
        or bilibili.is_bvid(value)
        or value.isdigit()
        or bool(peek_audio_source(value).get("kind"))
    )


def resolve_audio_source(
    song_id: str, title: str = "", artist: str = ""
) -> dict[str, Any]:
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
    return (
        _resolve_netease_source(song_id, title)
        or _resolve_bilibili_source(song_id, title, artist)
        or (cached if cached.get("kind") in {"netease", "ytdlp"} else {})
        or _resolve_ytdlp_source(song_id, title, artist, ("soundcloud",))
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


def open_preview_stream(
    song_id: str, title: str = "", artist: str = "", media: str = ""
):
    from lovktv.catalog.mugen import is_mugen_kid, open_mugen_preview

    if is_mugen_kid(song_id):
        return open_mugen_preview(song_id, media_name=media), {
            "kind": "mugen",
            "title": title,
        }
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
