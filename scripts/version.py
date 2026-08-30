#!/usr/bin/env python3
"""Repo version for APKs, catalog labels, and git tags.

  python scripts/version.py
  python scripts/version.py tag
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = ROOT / "VERSION"


def read_version() -> tuple[str, int]:
    name = "0.0.0"
    code = 1
    if VERSION_PATH.is_file():
        for raw in VERSION_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("name="):
                name = line.split("=", 1)[1].strip() or name
            elif line.startswith("code="):
                try:
                    code = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
    return name, code


def write_version(name: str, code: int) -> None:
    VERSION_PATH.write_text(f"name={name}\ncode={code}\n", encoding="utf-8")


def tag_name(name: str) -> str:
    text = re.sub(r"[^\w.\-+]", "", (name or "").strip())
    return f"v{text}" if text else ""


def git_tag(name: str, message: str = "") -> int:
    tag = tag_name(name)
    if not tag:
        print("missing version name", file=sys.stderr)
        return 1
    existing = subprocess.run(
        ["git", "tag", "-l", tag],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if (existing.stdout or "").strip() == tag:
        print(f"tag exists: {tag}")
        return 0
    note = message or f"lov-ktv {name}"
    proc = subprocess.run(
        ["git", "tag", "-a", tag, "-m", note],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "git tag failed\n")
        return proc.returncode
    print(tag)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Read or tag the lov-ktv VERSION")
    parser.add_argument("action", nargs="?", default="show", choices=("show", "tag"))
    args = parser.parse_args()
    name, code = read_version()
    if args.action == "tag":
        return git_tag(name)
    print(f"{name}  {code}  {tag_name(name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
