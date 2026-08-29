from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from lovktv.core.config import PUBLIC_URL, SESSION_DAYS
from lovktv.identity.auth import SESSION_COOKIE, public_base
from lovktv.locale.i18n import t as i18n_t
from lovktv.storage.store import user_from_session


def request_base(request) -> str:
    if PUBLIC_URL:
        return PUBLIC_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}"


def current_user(request):
    return user_from_session(request.cookies.get(SESSION_COOKIE) or "")


def set_session(response, token: str, request) -> None:
    secure = request.url.scheme == "https" or public_base().startswith("https")
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )


def clear_session(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def fail(request, status: int, key: str, **vars) -> None:
    raise HTTPException(status, i18n_t(request, key, **vars))


def set_host_cookie(response: JSONResponse, request, token: str) -> JSONResponse:
    if token:
        secure = request.url.scheme == "https" or public_base().startswith("https")
        response.set_cookie(
            "lovktv_host",
            token,
            max_age=400 * 86400,
            httponly=True,
            samesite="lax",
            path="/",
            secure=secure,
        )
    return response
