"""Runtime state shared by API routers."""

from __future__ import annotations

from fastapi import WebSocket

from lovktv import config
from lovktv.host_volume import host_volume_meta as _host_volume_meta
from lovktv.host_volume import set_host_volume as _set_host_volume

_rooms: dict[str, set[WebSocket]] = {}
_peers: dict[WebSocket, dict] = {}
_mics: dict[str, str] = {}


def media_dir():
    return config.MEDIA_DIR


def web_root():
    dist = config.ROOT / "frontend" / "frontend-dist"
    return (
        dist
        if (dist / "manifest.json").is_file()
        else config.ROOT / "frontend" / "public"
    )


def host_volume_meta():
    return _host_volume_meta()


def set_host_volume(value: int):
    return _set_host_volume(value)
