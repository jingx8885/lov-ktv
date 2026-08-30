#!/usr/bin/env python3
"""Upload TV / phone APKs to the public process server.

APKs stay on the server data volume. They are not committed to git.

  set LOVKTV_APP_UPLOAD_TOKEN=...
  python scripts/publish-apps.py --tv path/to/tv.apk --phone path/to/phone.apk --version 2026.8.30

Default --version is VERSION name. Tag with: python scripts/version.py tag

Defaults: LOVKTV_PUBLIC_URL or https://ktv.lovbrowser.com
Optional paths fall back to local Gradle outputs if they exist.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from version import read_version  # noqa: E402
DEFAULT_BASE = "https://ktv.lovbrowser.com"
CHANNELS = ("tv", "phone")
DEFAULT_APKS = {
    "tv": (
        ROOT / "android-tv" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
        ROOT / "android-tv" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk",
    ),
    "phone": (
        ROOT / "android-phone" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk",
        ROOT / "android-phone" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
    ),
}


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _multipart(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8") + b"\r\n")
    for name, path in files.items():
        filename = path.name.replace('"', "")
        mime = mimetypes.guess_type(filename)[0] or "application/vnd.android.package-archive"
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        chunks.append(f"Content-Type: {mime}\r\n\r\n".encode())
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _request(method: str, url: str, token: str = "", body: bytes | None = None, content_type: str = "") -> tuple[int, dict | str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    text = raw.decode("utf-8", "replace")
    try:
        return status, json.loads(text) if text else {}
    except json.JSONDecodeError:
        return status, text


def _print_catalog(base: str, data: dict) -> None:
    for channel in CHANNELS:
        item = data.get(channel) if isinstance(data, dict) else None
        if not item:
            print(f"{channel}: not published")
            continue
        url = str(item.get("url") or f"/apps/{channel}.apk")
        if url.startswith("/"):
            url = base + url
        print(f"{channel}: {item.get('version')}  {item.get('size')}  {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish lov-ktv TV/phone APKs")
    parser.add_argument("--base", default=(os.environ.get("LOVKTV_PUBLIC_URL") or DEFAULT_BASE).rstrip("/"))
    parser.add_argument("--token", default=os.environ.get("LOVKTV_APP_UPLOAD_TOKEN") or "")
    parser.add_argument("--tv", type=Path, help="TV APK path")
    parser.add_argument("--phone", type=Path, help="Phone APK path")
    parser.add_argument(
        "--version",
        default="",
        help="Version label stored in the catalog (default: VERSION file)",
    )
    parser.add_argument("--list", action="store_true", help="Print the public catalog and exit")
    args = parser.parse_args()
    base = str(args.base).rstrip("/")

    if args.list:
        status, data = _request("GET", f"{base}/api/apps")
        if status != 200:
            print(f"catalog failed: HTTP {status}", file=sys.stderr)
            return 1
        _print_catalog(base, data if isinstance(data, dict) else {})
        return 0

    uploads: list[tuple[str, Path]] = []
    for channel in CHANNELS:
        given = getattr(args, channel)
        path = Path(given) if given else _first_existing(DEFAULT_APKS[channel])
        if given and not path.is_file():
            print(f"missing {channel} apk: {path}", file=sys.stderr)
            return 1
        if path:
            uploads.append((channel, path))
    if not uploads:
        print("pass --tv and/or --phone, or build the Android apps first", file=sys.stderr)
        return 1
    token = str(args.token or "").strip()
    if not token:
        print("set LOVKTV_APP_UPLOAD_TOKEN or pass --token", file=sys.stderr)
        return 1
    version = str(args.version or "").strip() or read_version()[0]

    failed = 0
    for channel, path in uploads:
        fields = {}
        if version:
            fields["version"] = version
        body, content_type = _multipart(fields, {"file": path})
        status, data = _request("POST", f"{base}/api/apps/{channel}", token, body, content_type)
        if status != 200 or not isinstance(data, dict) or not data.get("url"):
            print(f"{channel}: upload failed HTTP {status}", file=sys.stderr)
            failed += 1
            continue
        url = str(data.get("url") or f"/apps/{channel}.apk")
        if url.startswith("/"):
            url = base + url
        print(f"{channel}: {data.get('version')}  {data.get('size')}  {url}")
    if failed:
        return 1
    status, catalog = _request("GET", f"{base}/api/apps")
    if status == 200 and isinstance(catalog, dict):
        print("catalog:")
        _print_catalog(base, catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
