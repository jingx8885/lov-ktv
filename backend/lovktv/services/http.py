from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from lovktv.core.config import SESSION_DAYS
from lovktv.identity.auth import SESSION_COOKIE
from lovktv.locale.i18n import t as i18n_t
from lovktv.storage.store import user_from_session


def request_base(request) -> str:
    from lovktv.storage import settings

    configured = settings.get("public_url")
    if configured:
        return configured.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}"


def request_secure(request) -> bool:
    """Whether *this* connection is TLS, so `Secure` cookies can survive.

    Never infer it from the configured public URL: the same process also
    answers plaintext LAN and TV-loopback origins, and a `Secure` cookie on
    a plaintext response is silently dropped by the browser, which reads to
    the user as "logged out again".
    """
    if request.url.scheme == "https":
        return True
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0]
    return proto.strip().lower() == "https"


def current_user(request):
    return user_from_session(request.cookies.get(SESSION_COOKIE) or "")


def set_session(response, token: str, request) -> None:
    secure = request_secure(request)
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
        secure = request_secure(request)
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
