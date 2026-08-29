#!/usr/bin/env python3
"""Smoke-test the public KTV deployment without requiring credentials.

Usage::

    .venv/bin/python scripts/accept-production.py
    .venv/bin/python scripts/accept-production.py --base http://127.0.0.1:18790

Only public GET endpoints are queried.  The script intentionally never reads
or prints tokens, cookies, or response headers containing credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_BASE = "https://ktv.lovbrowser.com"
PATHS = ("/", "/api/host", "/tv.html", "/m.html")


def fetch(base: str, path: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        f"{base}{path}",
        headers={"Accept": "application/json" if path == "/api/host" else "text/html"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check public lov-ktv endpoints")
    parser.add_argument("--base", default=os.environ.get("LOVKTV_PUBLIC_URL") or DEFAULT_BASE)
    parser.add_argument("--expect-origin", default="", help="Optional exact /api/host origin")
    args = parser.parse_args()
    base = str(args.base).rstrip("/")
    failed = False
    host: dict = {}
    for path in PATHS:
        status, body = fetch(base, path)
        ok = status == 200
        if path == "/api/host" and ok:
            try:
                host = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                ok = False
            if ok and args.expect_origin and host.get("origin") != args.expect_origin:
                print(f"{path}: expected origin {args.expect_origin!r}", file=sys.stderr)
                ok = False
            if ok and host.get("models", {}).get("separator") is not True:
                print(f"{path}: separator model is not ready", file=sys.stderr)
                ok = False
        print(f"{path}: HTTP {status} {'ok' if ok else 'FAILED'}")
        failed = failed or not ok
    if not failed:
        print(f"accept-production: {base} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
