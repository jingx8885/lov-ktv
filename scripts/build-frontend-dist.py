#!/usr/bin/env python3
"""Build the single frontend asset tree consumed by web and Android TV."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _files(root: Path) -> list[Path]:
    return sorted(
        (p for p in root.rglob("*") if p.is_file() and p.name not in {"manifest.json", ".DS_Store"}),
        key=lambda p: p.relative_to(root).as_posix(),
    )


def _digest(root: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    # Match ``lovktv.media.assets._compute`` ordering exactly on Windows and POSIX.
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_commit(root: Path) -> str:
    explicit = os.environ.get("LOVKTV_GIT_COMMIT", "").strip()
    if explicit:
        return explicit
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if not source.is_dir():
        raise SystemExit(f"frontend source directory does not exist: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        shutil.copytree(source, temporary, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".DS_Store"))
        copied = _files(temporary)
        content_sha256 = _digest(temporary, copied)
        manifest = {
            "schema": 1,
            "revision": content_sha256[:12],
            "content_sha256": content_sha256,
            "git_commit": _git_commit(source),
            "files": {
                p.relative_to(temporary).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in copied
            },
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            shutil.rmtree(output)
        temporary.replace(output)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("frontend/public"))
    parser.add_argument("--output", type=Path, default=Path("frontend/frontend-dist"))
    args = parser.parse_args()
    manifest = build(args.source, args.output)
    print(f"frontend-dist revision={manifest['revision']} files={len(manifest['files'])}")


if __name__ == "__main__":
    main()
