from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

ASSET_SUFFIXES = {".css", ".html", ".js"}
ASSET_REF_RE = re.compile(
    r"""(?P<prefix>url\(|['"`])(?P<path>(?:\.{1,2}/|/)(?:[\w.-]+/)*[\w.-]+\.(?:js|css))(?:\?v=[^'"`?\s#&]*)?(?P<suffix>['"`)])"""
)
_MEDIA = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

_cache: dict[str, tuple[tuple[int, int], str]] = {}


def reset_asset_rev_cache() -> None:
    _cache.clear()


def _stamp(root: Path) -> tuple[int, int]:
    total = 0
    count = 0
    for path in root.rglob("*"):
        if path.is_file() and path.name not in {"manifest.json", ".DS_Store"}:
            stat = path.stat()
            total += stat.st_mtime_ns + stat.st_size
            count += 1
    return total, count


def _compute(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.name not in {"manifest.json", ".DS_Store"}
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def asset_rev(root: Path) -> str:
    pinned = (os.environ.get("LOVKTV_ASSET_REV") or "").strip()
    if pinned:
        return pinned[:32]
    key = str(root.resolve())
    manifest = root / "manifest.json"
    if manifest.is_file():
        try:
            revision = str(
                json.loads(manifest.read_text(encoding="utf-8")).get("revision", "")
            ).strip()
            if revision:
                return revision[:32]
        except (OSError, ValueError, TypeError):
            pass
    stamp = _stamp(root)
    hit = _cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    rev = _compute(root)[:12]
    _cache[key] = (stamp, rev)
    return rev


def rewrite_frontend_assets(text: str, rev: str) -> str:
    if not rev:
        return text

    def repl(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{match.group('path')}?v={rev}{match.group('suffix')}"

    return ASSET_REF_RE.sub(repl, text)


def versioned_headers(path: Path) -> dict[str, str]:
    if path.suffix.lower() == ".html" or path.name == "manifest.json":
        return {
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "CDN-Cache-Control": "no-store",
        }
    return {"Cache-Control": "public, max-age=31536000, immutable"}


def versioned_response(path: Path, root: Path, status_code: int = 200) -> Response:
    body = rewrite_frontend_assets(
        path.read_text(encoding="utf-8"), asset_rev(root)
    ).encode("utf-8")
    return Response(
        content=body,
        status_code=status_code,
        media_type=_MEDIA.get(path.suffix.lower(), "application/octet-stream"),
        headers=versioned_headers(path),
    )


class VersionedStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.asset_root = Path(str(self.directory))

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        file_path = getattr(response, "path", None)
        if not file_path or getattr(response, "status_code", 200) != 200:
            return response
        full = Path(file_path)
        if full.suffix.lower() not in ASSET_SUFFIXES and full.name != "manifest.json":
            return response
        rewritten = versioned_response(
            full, self.asset_root, status_code=response.status_code
        )
        if scope.get("method") == "HEAD":
            return Response(
                content=b"",
                status_code=rewritten.status_code,
                media_type=rewritten.media_type,
                headers=dict(rewritten.headers),
            )
        return rewritten
