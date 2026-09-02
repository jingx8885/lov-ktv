"""Admin token gate. Never log or return the secret."""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from lovktv.locale.i18n import t as i18n_t

ADMIN_COOKIE = "lovktv_admin"


def admin_token() -> str:
    return (
        os.environ.get("LOVKTV_ADMIN_TOKEN")
        or os.environ.get("LOVKTV_APP_UPLOAD_TOKEN")
        or ""
    ).strip()


def _given_token(request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = (request.headers.get("x-lovktv-token") or "").strip()
    if header:
        return header
    return (request.cookies.get(ADMIN_COOKIE) or "").strip()


def require_admin(request) -> None:
    expected = admin_token()
    if not expected:
        raise HTTPException(503, i18n_t(request, "api.admin_not_configured"))
    given = _given_token(request)
    if not given or not hmac.compare_digest(given, expected):
        raise HTTPException(401, i18n_t(request, "api.admin_unauthorized"))


def set_admin_cookie(response: JSONResponse, request, token: str) -> None:
    from lovktv.services.http import request_secure

    secure = request_secure(request)
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=14 * 86400,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )


def clear_admin_cookie(response: JSONResponse) -> None:
    response.delete_cookie(ADMIN_COOKIE, path="/")
