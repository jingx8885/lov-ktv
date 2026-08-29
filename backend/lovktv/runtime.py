"""Runtime state and compatibility helpers shared by API routers.

The helpers intentionally resolve mutable values from :mod:`lovktv.main` at
call time.  This keeps the historical ``main.MEDIA_DIR`` and host-volume
monkeypatch points working while routers are split into focused modules.
"""
from __future__ import annotations

from fastapi import WebSocket

_rooms: dict[str, set[WebSocket]] = {}
_peers: dict[WebSocket, dict] = {}
_mics: dict[str, str] = {}


def media_dir():
    from lovktv import main

    return main.MEDIA_DIR


def web_root():
    from lovktv import main

    return main.WEB


def host_volume_meta():
    from lovktv import main

    return main.host_volume_meta()


def set_host_volume(value: int):
    from lovktv import main

    return main.set_host_volume(value)
