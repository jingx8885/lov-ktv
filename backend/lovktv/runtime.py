"""Process-local runtime state shared by API routers."""

from __future__ import annotations

from fastapi import WebSocket

_rooms: dict[str, set[WebSocket]] = {}
_peers: dict[WebSocket, dict] = {}
_mics: dict[str, str] = {}


def web_root():
    from lovktv.config import ROOT

    dist = ROOT / "frontend" / "frontend-dist"
    public = ROOT / "frontend" / "public"
    return dist if (dist / "manifest.json").is_file() else public
