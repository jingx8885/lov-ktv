"""NetEase play URL via eapi.

The public outer link `music.163.com/song/media/outer/url` 302s to /404.
NeteaseCloudMusicApi / api-enhanced get the real CDN URL from
`/eapi/song/enhance/player/url` with AES-ECB and a China X-Real-IP.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import urllib.parse
import urllib.request
from typing import Any

from lovktv.catalog.http import urlopen

EAPI_KEY = b"e82ckenh8dichen8"
EAPI_PATH = "/api/song/enhance/player/url"
EAPI_URL = "https://interface3.music.163.com/eapi/song/enhance/player/url"
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 "
    "NeteaseMusicDesktop/3.1.29.205117"
)


def china_ip() -> str:
    return f"116.{random.randint(25, 94)}.{random.randint(1, 254)}.{random.randint(1, 254)}"


def aes_ecb_encrypt(plain: bytes, key: bytes = EAPI_KEY) -> bytes:
    """Encrypt EAPI payloads without requiring a system OpenSSL binary.

    PyCryptodome is used in normal deployments so Windows and slim containers
    behave like Linux hosts.  Keep the subprocess fallback for installations
    that deliberately omit the optional crypto wheel.
    """
    try:
        from Crypto.Cipher import AES

        pad = 16 - (len(plain) % 16)
        return AES.new(key, AES.MODE_ECB).encrypt(plain + bytes([pad]) * pad)
    except ImportError:
        pass
    result = subprocess.run(
        ["openssl", "enc", "-aes-128-ecb", "-K", key.hex(), "-nosalt"],
        input=plain,
        capture_output=True,
        check=True,
        timeout=5,
    )
    return result.stdout


def eapi_params(payload: dict[str, Any], api_path: str = EAPI_PATH) -> str:
    text = json.dumps(payload, separators=(",", ":"))
    digest = hashlib.md5(f"nobody{api_path}use{text}md5forencrypt".encode()).hexdigest()
    blob = f"{api_path}-36cd479b6b5-{text}-36cd479b6b5-{digest}"
    return aes_ecb_encrypt(blob.encode()).hex().upper()


def eapi_headers(real_ip: str | None = None) -> dict[str, str]:
    ip = real_ip or china_ip()
    return {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://music.163.com/",
        "Origin": "https://music.163.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Real-IP": ip,
        "X-Forwarded-For": ip,
        "Cookie": "os=pc; appver=3.1.17.204416",
    }


def eapi_play_url(song_id: str, timeout: float = 12) -> str:
    song_id = str(song_id or "").strip()
    if not song_id.isdigit():
        return ""
    body = urllib.parse.urlencode(
        {"params": eapi_params({"ids": f"[{song_id}]", "br": 320000})}
    ).encode()
    req = urllib.request.Request(EAPI_URL, data=body, headers=eapi_headers())
    for _attempt in range(2):
        try:
            with urlopen(req, timeout=timeout, via_proxy=True) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        item = (data.get("data") or [{}])[0] if isinstance(data, dict) else {}
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url:
            return url
    return ""


def media_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"User-Agent": DESKTOP_UA, "Referer": "https://music.163.com/"},
    )
