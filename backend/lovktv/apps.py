"""Public APK catalog. Files live on the data volume, not in git or the image."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

CHANNELS = ("tv", "phone")
DISPLAY_NAME = {"tv": "lovktv-tv.apk", "phone": "lovktv-phone.apk"}
MAX_BYTES = 80 * 1024 * 1024
APK_MIME = "application/vnd.android.package-archive"


def apps_dir() -> Path:
    root = Path(os.environ.get("LOVKTV_DATA") or Path(__file__).resolve().parents[2] / "data")
    return root.resolve() / "apps"


def upload_token() -> str:
    return (os.environ.get("LOVKTV_APP_UPLOAD_TOKEN") or "").strip()


def normalize_channel(channel: str) -> str:
    name = (channel or "").strip().lower().removesuffix(".apk")
    if name not in CHANNELS:
        raise HTTPException(404, "unknown app")
    return name


def _manifest_path() -> Path:
    return apps_dir() / "manifest.json"


def _apk_path(channel: str) -> Path:
    return apps_dir() / f"{channel}.apk"


def load_manifest() -> dict:
    path = _manifest_path()
    if not path.is_file():
        return {name: None for name in CHANNELS}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {name: None for name in CHANNELS}
    if not isinstance(raw, dict):
        return {name: None for name in CHANNELS}
    return {name: raw.get(name) if isinstance(raw.get(name), dict) else None for name in CHANNELS}


def _write_manifest(data: dict) -> None:
    folder = apps_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / ".manifest.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, _manifest_path())


def _public_item(channel: str, row: dict | None) -> dict | None:
    if not row:
        return None
    apk = _apk_path(channel)
    if not apk.is_file():
        return None
    size = int(row.get("size") or apk.stat().st_size)
    return {
        "channel": channel,
        "version": str(row.get("version") or ""),
        "size": size,
        "sha256": str(row.get("sha256") or ""),
        "filename": DISPLAY_NAME[channel],
        "updated_at": str(row.get("updated_at") or ""),
        "url": f"/apps/{channel}.apk",
    }


def catalog() -> dict:
    stored = load_manifest()
    return {name: _public_item(name, stored.get(name)) for name in CHANNELS}


def clean_version(raw: str) -> str:
    text = re.sub(r"[^\w.\-+]", "", (raw or "").strip())[:40]
    return text or datetime.now(timezone.utc).strftime("%Y.%m.%d")


def _request_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-lovktv-token") or "").strip()


def require_upload_token(request: Request) -> None:
    expected = upload_token()
    if not expected:
        raise HTTPException(503, "app upload is not configured")
    given = _request_token(request)
    if not given or not hmac.compare_digest(given, expected):
        raise HTTPException(401, "unauthorized")


def save_apk(channel: str, stream, version: str = "") -> dict:
    name = normalize_channel(channel)
    folder = apps_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = _apk_path(name)
    tmp = folder / f".{name}.apk.tmp"
    try:
        with tmp.open("wb") as handle:
            shutil.copyfileobj(stream, handle)
            size = handle.tell()
        if size < 64:
            raise HTTPException(400, "apk empty")
        if size > MAX_BYTES:
            raise HTTPException(413, "apk too large")
        hasher = hashlib.sha256()
        with tmp.open("rb") as handle:
            if handle.read(2) != b"PK":
                raise HTTPException(400, "not an apk")
            handle.seek(0)
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        digest = hasher.hexdigest()
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    row = {
        "version": clean_version(version),
        "size": size,
        "sha256": digest,
        "filename": DISPLAY_NAME[name],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    stored = load_manifest()
    stored[name] = row
    _write_manifest(stored)
    return _public_item(name, row) or row


def download_apk(channel: str) -> FileResponse:
    name = normalize_channel(channel)
    path = _apk_path(name)
    if not path.is_file():
        raise HTTPException(404, "app not published")
    filename = DISPLAY_NAME[name]
    return FileResponse(
        path,
        media_type=APK_MIME,
        filename=filename,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
