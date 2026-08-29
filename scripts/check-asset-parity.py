#!/usr/bin/env python3
"""Compare a TV APK/AAB web bundle with the canonical frontend-dist tree.

The command is intentionally usable in CI without an Android SDK.  When no
artifact is available it prints ``SKIP`` and exits successfully; pass
``--require-artifact`` to make a missing artifact an error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENTRIES = ("index.html", "tv.html", "m.html")


@dataclass(frozen=True)
class Bundle:
    """A bundle's manifest and raw (or URL-normalized) file bytes."""

    manifest: Mapping[str, object]
    files: Mapping[str, bytes]


def _manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest: {path} ({exc})") from exc
    if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
        raise TypeError(f"manifest has no files map: {path}")
    return value


def _files_map(manifest: Mapping[str, object]) -> Mapping[str, object]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise TypeError("manifest has no files map")
    return files


def from_directory(root: Path) -> Bundle:
    """Read a built ``frontend-dist`` directory."""

    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"bundle directory does not exist: {root}")
    manifest = _manifest(root / "manifest.json")
    files: dict[str, bytes] = {}
    for relative in _files_map(manifest):
        if not isinstance(relative, str):
            raise TypeError("manifest file path is not a string")
        path = root / relative
        if not path.is_file():
            raise ValueError(f"manifest references missing file: {relative}")
        files[relative] = path.read_bytes()
    listed = set(files)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", ".DS_Store"}
    }
    for relative in sorted(actual - listed):
        files[relative] = (root / relative).read_bytes()
    return Bundle(manifest, files)


def _zip_prefix(names: list[str]) -> str:
    matches = [name for name in names if name.endswith("assets/web/manifest.json")]
    if not matches:
        raise ValueError("artifact has no assets/web/manifest.json")
    if len(matches) > 1:
        raise ValueError("artifact has multiple assets/web/manifest.json entries")
    return matches[0][: -len("manifest.json")]


def from_archive(path: Path) -> Bundle:
    """Read web assets from an APK, AAB, or any zip with assets/web."""

    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            prefix = _zip_prefix(names)
            try:
                manifest = json.loads(archive.read(prefix + "manifest.json"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid embedded manifest: {path}") from exc
            if not isinstance(manifest, dict) or not isinstance(
                manifest.get("files"), dict
            ):
                raise TypeError("embedded manifest has no files map")
            files: dict[str, bytes] = {}
            embedded = {
                name[len(prefix) :]
                for name in names
                if name.startswith(prefix)
                and name != prefix + "manifest.json"
                and not name.endswith("/")
            }
            for relative in _files_map(manifest):
                if not isinstance(relative, str):
                    raise TypeError("embedded manifest file path is not a string")
                name = prefix + relative
                try:
                    files[relative] = archive.read(name)
                except KeyError as exc:
                    raise ValueError(
                        f"artifact missing embedded file: {relative}"
                    ) from exc
            for relative in sorted(embedded - set(files)):
                files[relative] = archive.read(prefix + relative)
            return Bundle(manifest, files)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"cannot read artifact {path}: {exc}") from exc


def _url_bytes(base: str, relative: str) -> bytes:
    url = base.rstrip("/") + "/" + relative
    request = urllib.request.Request(url, headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise ValueError(f"failed to fetch {url}: {exc}") from exc


def from_url(base: str) -> Bundle:
    """Fetch a public bundle's manifest and files.

    HTML/CSS/JS responses are served with revision query strings injected;
    those URLs are removed before hashing so they can be compared to the raw
    frontend-dist bytes.
    """

    raw = _url_bytes(base, "manifest.json")
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid remote manifest: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise TypeError("remote manifest has no files map")
    revision = str(manifest.get("revision", ""))
    files: dict[str, bytes] = {}
    for relative in _files_map(manifest):
        if not isinstance(relative, str):
            raise TypeError("remote manifest file path is not a string")
        data = _url_bytes(base, relative)
        if revision and relative.rsplit(".", 1)[-1].lower() in {"html", "js", "css"}:
            data = data.decode("utf-8").replace(f"?v={revision}", "").encode("utf-8")
        files[relative] = data
    return Bundle(manifest, files)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_hash(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[relative])
        digest.update(b"\0")
    return digest.hexdigest()


def _validate(label: str, bundle: Bundle) -> list[str]:
    failures: list[str] = []
    declared = _files_map(bundle.manifest)
    for relative in sorted(set(declared) & set(bundle.files)):
        expected = str(declared[relative])
        actual = _hash(bundle.files[relative])
        if expected != actual:
            failures.append(
                f"{label} manifest hash mismatch: {relative} ({actual} != {expected})"
            )
    content_hash = _content_hash(bundle.files)
    expected_content = str(bundle.manifest.get("content_sha256", ""))
    if expected_content != content_hash:
        failures.append(
            f"{label} content_sha256 mismatch: {content_hash} != {expected_content}"
        )
    revision = str(bundle.manifest.get("revision", ""))
    if revision != content_hash[:12]:
        failures.append(
            f"{label} revision is not content hash prefix: {revision!r} != {content_hash[:12]!r}"
        )
    return failures


def compare(
    reference: Bundle, artifact: Bundle, entries: tuple[str, ...] = DEFAULT_ENTRIES
) -> list[str]:
    """Return human-readable parity failures (empty means parity passed)."""

    failures = _validate("reference", reference) + _validate("artifact", artifact)
    ref_paths = set(reference.files)
    artifact_paths = set(artifact.files)
    if ref_paths != artifact_paths:
        missing = sorted(ref_paths - artifact_paths)
        extra = sorted(artifact_paths - ref_paths)
        if missing:
            failures.append("missing paths: " + ", ".join(missing))
        if extra:
            failures.append("unexpected paths: " + ", ".join(extra))

    if reference.manifest.get("revision") != artifact.manifest.get("revision"):
        failures.append(
            f"manifest revision mismatch: {reference.manifest.get('revision')!r} != {artifact.manifest.get('revision')!r}"
        )
    for relative in sorted(ref_paths & artifact_paths):
        expected = str(_files_map(reference.manifest).get(relative, ""))
        actual = _hash(artifact.files[relative])
        if expected != actual:
            failures.append(f"hash mismatch: {relative} ({actual} != {expected})")
    for relative in entries:
        if relative in reference.files and relative in artifact.files:
            expected, actual = (
                _hash(reference.files[relative]),
                _hash(artifact.files[relative]),
            )
            if expected != actual:
                failures.append(
                    f"entry hash mismatch: {relative} ({actual} != {expected})"
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, help="TV APK/AAB/zip to inspect")
    references = parser.add_mutually_exclusive_group()
    references.add_argument(
        "--reference", type=Path, default=Path("frontend/frontend-dist")
    )
    references.add_argument(
        "--public-url",
        help="Use a deployed bundle as the reference instead of --reference",
    )
    parser.add_argument(
        "--require-artifact", action="store_true", help="fail when --artifact is absent"
    )
    parser.add_argument(
        "--entry",
        action="append",
        dest="entries",
        help="entry path to compare (repeatable)",
    )
    args = parser.parse_args(argv)
    if args.artifact is None:
        message = "asset parity: no APK/AAB artifact; SKIP (use --require-artifact to enforce)"
        print(message)
        return 2 if args.require_artifact else 0
    if not args.artifact.is_file():
        print(f"asset parity: artifact not found: {args.artifact}", file=sys.stderr)
        return 2
    try:
        reference = (
            from_url(args.public_url)
            if args.public_url
            else from_directory(args.reference)
        )
        artifact = from_archive(args.artifact)
        failures = compare(reference, artifact, tuple(args.entries or DEFAULT_ENTRIES))
    except (TypeError, ValueError) as exc:
        print(f"asset parity: ERROR: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("asset parity: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        f"asset parity: OK ({args.artifact}) revision={artifact.manifest.get('revision')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
