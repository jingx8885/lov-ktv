"""Audio source cache and provider adapters."""
from __future__ import annotations
import subprocess, shutil
from pathlib import Path
from typing import Any
from lovktv.catalog import bilibili
from lovktv.catalog.http import curl_proxy_args, urlopen, ytdlp_proxy_args
from lovktv.catalog.netease import eapi_play_url, media_request
from .search import BROWSER_UA, clean_search_title, is_clean_title

_AUDIO_CACHE: dict[str, dict[str, Any]] = {}
def remember_audio_source(song_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if song_id: _AUDIO_CACHE[str(song_id)] = payload
    return payload
def forget_audio_source(song_id: str) -> None: _AUDIO_CACHE.pop(str(song_id) or "", None)
def peek_audio_source(song_id: str) -> dict[str, Any]: return dict(_AUDIO_CACHE.get(str(song_id) or "") or {})

def probe_netease_url(song_id: str) -> bool: return bool(eapi_play_url(song_id))
def open_netease_audio(song_id: str, timeout: float = 20):
    url = eapi_play_url(song_id)
    if not url: return None
    try: resp = urlopen(media_request(url), timeout=timeout, via_proxy=True)
    except Exception: return None
    final, ctype = str(resp.geturl() or ""), str(resp.headers.get("Content-Type") or "").lower()
    if "/404" in final or "text/html" in ctype:
        try: resp.close()
        except Exception: pass
        return None
    return resp

def try_netease_download(song_id: str, out_path: Path) -> bool:
    url = eapi_play_url(song_id)
    if not url: return False
    cmd = ["curl", "-sL", "-o", str(out_path), "-w", "%{http_code}\n%{url_effective}\n", "-A", "Mozilla/5.0", "-e", "https://music.163.com/", *curl_proxy_args(), url]
    try: result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError): return False
    info = result.stdout.strip().splitlines(); status = info[0] if info else ""; final_url = info[1] if len(info) > 1 else ""
    if status.startswith("2") and "/404" not in final_url and out_path.exists() and out_path.stat().st_size > 50_000: return True
    if out_path.exists(): out_path.unlink()
    return False

def _ytdlp_download(page_url: str, out_path: Path) -> bool:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not page_url: return False
    cmd = [ytdlp, "-x", "--audio-format", "mp3", "--audio-quality", "0", "-o", str(out_path.with_suffix(".%(ext)s")), "--no-playlist", "--quiet", "--no-warnings", "--force-overwrites", *ytdlp_proxy_args(), page_url]
    try: result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired: return False
    if result.returncode != 0: return False
    if out_path.exists() and out_path.stat().st_size > 50_000: return True
    for ext in (".m4a", ".opus", ".webm"):
        alt = out_path.with_suffix(ext)
        if alt.exists() and alt.stat().st_size > 50_000:
            alt.rename(out_path)
            return True
    return False

def _ytdlp_direct_url(page_url: str) -> str:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not page_url: return ""
    cmd = [ytdlp, "-f", "bestaudio/best", "--get-url", "--no-playlist", "--quiet", "--no-warnings", *ytdlp_proxy_args(), page_url]
    try: result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError): return ""
    line = (result.stdout or "").strip().splitlines()
    return line[0] if line and result.returncode == 0 else ""

def _pick_best_match(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((cand for cand in candidates if is_clean_title(str(cand.get("title") or ""))), None)

def try_ytdlp_search(query: str, out_path: Path, provider: str) -> tuple[bool, str]:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp: return False, ""
    from lovktv.catalog import fetch as facade
    best = _pick_best_match(facade._list_ytdlp(query, ytdlp, provider))
    if best is None: return False, ""
    return _ytdlp_download(str(best["url"]), out_path), str(best.get("title") or "")

def pick_bilibili_mv(title: str, artist: str = "") -> dict[str, Any] | None: return bilibili.pick_mv(title, artist)
def try_bilibili_download(bvid: str, mp3_path: Path, video_path: Path | None = None) -> bool: return bilibili.download_mv(bvid, mp3_path, video_path)
def open_bilibili_audio(bvid: str, timeout: float = 20): return bilibili.open_audio(bvid, timeout=timeout)

def _resolve_bilibili_source(song_id: str, title: str = "", artist: str = "") -> dict[str, Any]:
    from lovktv.catalog import fetch as facade
    hit = facade.pick_bilibili_mv(title, artist)
    if not hit:
        cleaned = facade.clean_search_title(title)
        if cleaned and cleaned != title: hit = facade.pick_bilibili_mv(cleaned, "")
    if not hit: return {}
    urls = bilibili.play_urls(str(hit.get("bvid") or ""))
    if not urls.get("audio_url"): return {}
    return remember_audio_source(song_id, {"kind": "bilibili", "bvid": hit["bvid"], "title": str(hit.get("title") or title), "cover": str(hit.get("pic") or urls.get("cover") or "")})

def _resolve_netease_source(song_id: str, title: str = "") -> dict[str, Any]:
    from lovktv.catalog import fetch as facade
    if song_id and facade.probe_netease_url(song_id): return remember_audio_source(song_id, {"kind": "netease", "id": song_id, "title": title})
    return {}
