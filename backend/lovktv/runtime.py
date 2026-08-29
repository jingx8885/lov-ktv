"""Process-local runtime state shared by API routers."""

from __future__ import annotations

from fastapi import WebSocket

from lovktv import config

_rooms: dict[str, set[WebSocket]] = {}
_peers: dict[WebSocket, dict] = {}
_mics: dict[str, str] = {}


def media_root():
    """Return the configured media directory at call time."""
    return config.MEDIA_DIR


WEB_ROOT = (
    config.ROOT / "frontend" / "frontend-dist"
    if (config.ROOT / "frontend" / "frontend-dist" / "manifest.json").is_file()
    else config.ROOT / "frontend" / "public"
)
