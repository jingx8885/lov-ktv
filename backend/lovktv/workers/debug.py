"""Opt-in, per-song processing traces for the admin console.

Tracing is deliberately best-effort: a broken debug file must never make a
song job fail.  The trace contains only metadata and step outcomes; large
media files remain in the song folder and can be inspected through the
existing media endpoint.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from lovktv.core.config import MEDIA_DIR
from lovktv.storage import settings

TRACE_NAME = "processing-debug.json"
TRACE_SCHEMA = "lovktv-processing-debug-v1"


def enabled() -> bool:
    """Return whether the admin-requested processing trace is enabled.

    ``asr_debug`` predates the full pipeline trace, so keep it as an alias for
    backwards compatibility with existing deployments and environment files.
    """

    try:
        return bool(settings.get("processing_debug") or settings.get("asr_debug"))
    except Exception:
        value = str(
            os.environ.get("LOVKTV_PROCESSING_DEBUG")
            or os.environ.get("LOVKTV_ASR_DEBUG")
            or ""
        ).lower()
        return value in {"1", "true", "yes", "on"}


def trace_path(song_id: str, media_dir: Path | None = None) -> Path:
    if media_dir is None:
        try:
            # The store is monkey-patchable in tests and can be rebound by
            # embedded deployments; follow that runtime media root.
            from lovktv.storage import store

            media_dir = store.MEDIA_DIR
        except Exception:
            media_dir = MEDIA_DIR
    return Path(media_dir) / str(song_id) / TRACE_NAME


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{TRACE_NAME}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def start(song_id: str, kind: str) -> None:
    if not enabled():
        return
    path = trace_path(song_id)
    value = {
        "schema": TRACE_SCHEMA,
        "song_id": str(song_id),
        "kind": str(kind),
        "started_at": time.time(),
        "status": "running",
        "events": [],
    }
    try:
        _write(path, value)
    except Exception:
        pass


def event(song_id: str, phase: str, status: str = "ok", **detail: Any) -> None:
    if not enabled():
        return
    path = trace_path(song_id)
    try:
        value = _read(path)
        if not value:
            start(song_id, "unknown")
            value = _read(path)
        events = value.setdefault("events", [])
        if not isinstance(events, list):
            events = []
            value["events"] = events
        item: dict[str, Any] = {"at": time.time(), "phase": str(phase), "status": str(status)}
        item.update({key: val for key, val in detail.items() if val is not None})
        events.append(item)
        value["updated_at"] = item["at"]
        _write(path, value)
    except Exception:
        pass


def finish(song_id: str, status: str, error: str = "") -> None:
    if not enabled():
        return
    path = trace_path(song_id)
    try:
        value = _read(path)
        if not value:
            return
        value["status"] = str(status)
        value["error"] = str(error or "")
        value["finished_at"] = time.time()
        _write(path, value)
    except Exception:
        pass


def snapshot(song_id: str) -> dict[str, Any] | None:
    path = trace_path(song_id)
    if not path.exists():
        return None
    value = _read(path)
    return value or None
