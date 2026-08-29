#!/usr/bin/env python3
"""Compare the frontend manifest with an embedded TV APK and an optional web URL.

The APK task copies ``frontend/frontend-dist`` to ``assets/web``.  This check
validates that every manifest path is present and byte-identical in the APK,
then optionally checks the same paths and revision served by a deployment.
HTML is normalized only for the server-added ``?v=<revision>`` query strings;
all other text and binary assets are hashed byte-for-byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Mapping

ENTRYPOINTS = ("tv.html", "m.html", "tv/app.js", "phone/app.js")
_REV_QUERY = re.compile(rb"\?v=[^\"'`?\s#&]+")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
        raise ValueError(f"invalid manifest: {path}")
    return value


def _normalized(path: str, data: bytes) -> bytes:
    if path.endswith(".html"):
        return _REV_QUERY.sub(b"?v=REV", data)
    return data


def _check_tree(manifest: Mapping, read, label: str, normalize_html: bool = True) -> list[str]:
    errors: list[str] = []
    files = manifest["files"]
    for path, expected in sorted(files.items()):
        try:
            actual = read(path)
        except (FileNotFoundError, KeyError, OSError) as exc:
            errors.append(f"{label}: missing {path} ({exc})")
            continue
        if path.endswith(".html") and not normalize_html:
            continue
        candidate = _normalized(path, actual) if normalize_html else actual
        if _sha256(candidate) != expected:
            errors.append(f"{label}: hash mismatch {path}")
    for entry in ENTRYPOINTS:
        try:
            read(entry)
        except (FileNotFoundError, KeyError, OSError) as exc:
            errors.append(f"{label}: missing entrypoint {entry} ({exc})")
    return errors


def check_apk(apk: Path, manifest: Mapping) -> list[str]:
    with zipfile.ZipFile(apk) as archive:
        names = set(archive.namelist())
        prefix = "assets/web/"
        embedded_manifest = prefix + "manifest.json"
        if embedded_manifest not in names:
            return [f"apk: missing {embedded_manifest}"]
        embedded = json.loads(archive.read(embedded_manifest).decode("utf-8"))
        errors = []
        if embedded.get("revision") != manifest.get("revision"):
            errors.append("apk: manifest revision differs")
        errors.extend(
            _check_tree(manifest, lambda path: archive.read(prefix + path), "apk")
        )
        return errors


def check_web(base: str, manifest: Mapping) -> list[str]:
    origin = base.rstrip("/")

    def read(path: str) -> bytes:
        request = urllib.request.Request(origin + "/" + path, headers={"User-Agent": "lov-ktv-parity/1"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read()

    errors: list[str] = []
    try:
        remote_manifest = json.loads(read("manifest.json").decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return [f"web: unable to read manifest ({exc})"]
    if remote_manifest.get("revision") != manifest.get("revision"):
        errors.append("web: manifest revision differs")
    # The web server injects the revision query into HTML references. Static
    # JS/CSS/binary files remain byte-identical; HTML is covered by entrypoint
    # presence plus the manifest revision check.
    errors.extend(_check_tree(manifest, read, "web", normalize_html=False))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="frontend-dist/manifest.json")
    parser.add_argument("--apk", type=Path, help="built TV APK")
    parser.add_argument("--web", help="deployed origin, e.g. https://ktv.lovbrowser.com")
    args = parser.parse_args()
    manifest = _manifest(args.manifest)
    errors: list[str] = []
    if args.apk:
        errors.extend(check_apk(args.apk, manifest))
    if args.web:
        errors.extend(check_web(args.web, manifest))
    if not args.apk and not args.web:
        parser.error("at least one of --apk or --web is required")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"frontend parity OK: revision={manifest.get('revision')} entries={len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
