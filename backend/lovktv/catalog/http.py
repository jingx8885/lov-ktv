"""Optional outbound proxy for NetEase / yt-dlp.

Production uses the lov-stock Clash sidecar on 43:
`LOVKTV_HTTPS_PROXY=http://lov-stock-clash:7890`.
Do not set process-wide HTTP_PROXY; only catalog fetches that need it
should go through Clash.
"""

from __future__ import annotations

import os
import urllib.request


def outbound_proxy() -> str:
    return (os.environ.get("LOVKTV_HTTPS_PROXY") or "").strip()


def proxy_args(flag: str) -> list[str]:
    proxy = outbound_proxy()
    return [flag, proxy] if proxy else []


def curl_proxy_args() -> list[str]:
    return proxy_args("-x")


def ytdlp_proxy_args() -> list[str]:
    return proxy_args("--proxy")


def urlopen(req: urllib.request.Request, timeout: float = 15, via_proxy: bool = False):
    proxy = outbound_proxy() if via_proxy else ""
    if not proxy:
        return urllib.request.urlopen(req, timeout=timeout)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )
    return opener.open(req, timeout=timeout)
