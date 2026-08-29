from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from starlette.requests import Request

from lovktv.assets import versioned_response
from lovktv.oss import oss_ready, public_url
from lovktv.runtime import WEB_ROOT, media_root

router = APIRouter()


@router.get("/media/{song_id}/{name}")
def media(song_id: str, name: str, request: Request):
    root = media_root().resolve()
    path = (root / song_id / name).resolve()
    if root not in path.parents:
        raise HTTPException(404)
    rev = (request.query_params.get("v") or "").strip()
    cache = (
        "public, max-age=31536000, immutable" if rev else "no-cache, must-revalidate"
    )
    if path.exists():
        return FileResponse(
            path, headers={"Access-Control-Allow-Origin": "*", "Cache-Control": cache}
        )
    if oss_ready():
        url = public_url(song_id, name)
        if rev:
            url = f"{url}?v={quote(rev, safe='')}"
        return RedirectResponse(url, status_code=302)
    raise HTTPException(404)


@router.get("/m.html")
def mobile_page():
    path = WEB_ROOT / "m.html"
    if not path.exists():
        raise HTTPException(404)
    return versioned_response(path, WEB_ROOT)


@router.get("/login.html")
def login_page():
    path = WEB_ROOT / "login.html"
    if not path.exists():
        raise HTTPException(404)
    return versioned_response(path, WEB_ROOT)
