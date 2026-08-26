from __future__ import annotations

import platform
import subprocess
import time

_cached: int | None = None
_cached_at = 0.0


def is_mac() -> bool:
    return platform.system() == "Darwin"


def get_host_volume() -> int | None:
    global _cached, _cached_at
    if not is_mac():
        return None
    if _cached is not None and (time.monotonic() - _cached_at) < 0.8:
        return _cached
    try:
        out = subprocess.check_output(
            ["osascript", "-e", "output volume of (get volume settings)"],
            text=True,
            timeout=2,
        )
        _cached = max(0, min(100, int(out.strip())))
        _cached_at = time.monotonic()
        return _cached
    except (OSError, subprocess.SubprocessError, ValueError):
        return _cached


def set_host_volume(volume: int) -> bool:
    global _cached, _cached_at
    volume = max(0, min(100, int(volume)))
    if not is_mac():
        return False
    try:
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {volume}"],
            check=True,
            timeout=2,
            capture_output=True,
            text=True,
        )
        _cached = volume
        _cached_at = time.monotonic()
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def host_volume_meta() -> dict[str, str | int]:
    if not is_mac():
        return {}
    current = get_host_volume()
    meta: dict[str, str | int] = {"host_volume_kind": "mac"}
    if current is not None:
        meta["host_volume"] = current
    return meta
