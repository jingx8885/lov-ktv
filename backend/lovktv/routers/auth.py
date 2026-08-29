from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.requests import Request

from lovktv.auth import (
    SESSION_COOKIE,
    auth_status,
    decode_state,
    done_login_path,
    encode_state,
    exchange_wechat_code,
    in_wechat,
    login_page_url,
    scan_login_url,
    wechat_authorize_url,
    wechat_ready,
)
from lovktv.i18n import localize_exc
from lovktv.services.http import (
    clear_session,
    current_user,
    fail,
    request_base,
    set_session,
)
from lovktv.store import (
    confirm_login_ticket,
    consume_confirmed_ticket,
    create_login_ticket,
    create_session,
    delete_session,
    get_login_ticket,
    upsert_device_user,
    upsert_wechat_user,
)

router = APIRouter()


@router.get("/api/auth/status")
def api_auth_status() -> dict:
    return auth_status()


@router.get("/api/auth/me")
def api_auth_me(request: Request) -> dict:
    return {"user": current_user(request)}


@router.post("/api/auth/logout")
def api_auth_logout(request: Request):
    delete_session(request.cookies.get(SESSION_COOKIE) or "")
    response = JSONResponse({"ok": True, "user": None})
    clear_session(response)
    return response


@router.post("/api/auth/device")
def api_auth_device(request: Request, payload: dict = Body(default={})) -> JSONResponse:
    try:
        user = upsert_device_user(
            str(payload.get("device_id") or ""), str(payload.get("nickname") or "")
        )
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    response = JSONResponse({"user": user})
    set_session(response, create_session(user["id"]), request)
    return response


@router.get("/api/auth/scan")
def api_auth_scan(
    request: Request, ticket: str = "", room: str = "", next: str = ""
) -> RedirectResponse:
    base = request_base(request)
    dest = done_login_path(ticket, room, next)
    user = current_user(request)
    if user:
        if ticket:
            try:
                confirm_login_ticket(ticket, user["id"])
            except ValueError:
                pass
        return RedirectResponse(
            dest if dest.startswith("http") else f"{base}{dest}", status_code=302
        )
    if in_wechat(request.headers.get("user-agent") or "") and wechat_ready("mp"):
        redirect_uri = f"{base}/api/auth/wechat/callback"
        state = encode_state("silent", ticket, dest)
        try:
            url = wechat_authorize_url(redirect_uri, state, silent=True)
        except ValueError as exc:
            raise HTTPException(400, localize_exc(request, exc)) from exc
        return RedirectResponse(url, status_code=302)
    return RedirectResponse(
        login_page_url(base, ticket=ticket, room=room, next_path=next), status_code=302
    )


@router.get("/api/auth/wechat/login")
def api_wechat_login(
    request: Request,
    silent: bool = False,
    quick: bool = False,
    ticket: str = "",
    next: str = "",
) -> RedirectResponse:
    use_silent = bool(silent) and wechat_ready("mp")
    use_quick = bool(quick) and wechat_ready("mp") and not use_silent
    if not (use_silent or use_quick):
        if not wechat_ready("web"):
            fail(request, 400, "api.wechat_not_configured")
    redirect_uri = f"{request_base(request)}/api/auth/wechat/callback"
    kind = "silent" if use_silent else "quick" if use_quick else "web"
    state = encode_state(kind, ticket, next)
    try:
        url = wechat_authorize_url(
            redirect_uri, state, quick=use_quick, silent=use_silent
        )
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return RedirectResponse(url, status_code=302)


@router.get("/api/auth/wechat/callback")
def api_wechat_callback(
    request: Request, code: str = "", state: str = ""
) -> RedirectResponse:
    kind, ticket, next_path = decode_state(state)
    base = request_base(request)
    if not code:
        return RedirectResponse(
            login_page_url(
                base, ticket=ticket, next_path=next_path, error="api.wechat_denied"
            ),
            302,
        )
    try:
        info = exchange_wechat_code(
            code, quick=kind == "quick", silent=kind in {"silent", "base"}
        )
        user = upsert_wechat_user(
            info["openid"],
            info.get("unionid") or "",
            info.get("nickname") or "",
            info.get("avatar") or "",
        )
    except ValueError as exc:
        return RedirectResponse(
            login_page_url(
                base,
                ticket=ticket,
                next_path=next_path,
                error=localize_exc(request, exc),
            ),
            302,
        )
    if ticket:
        try:
            confirm_login_ticket(ticket, user["id"])
        except ValueError:
            pass
    dest = done_login_path(ticket, "", next_path)
    if not dest.startswith("http"):
        dest = f"{base}{dest}"
    response = RedirectResponse(dest, status_code=302)
    set_session(response, create_session(user["id"]), request)
    return response


@router.post("/api/auth/qr")
def api_auth_qr(request: Request, payload: dict = Body(default={})) -> dict:
    ticket = create_login_ticket()
    room = str(payload.get("room") or "").upper()
    return {
        **ticket,
        "url": scan_login_url(
            request_base(request), ticket=ticket["ticket"], room=room
        ),
    }


@router.get("/api/auth/qr/{ticket}")
def api_auth_qr_status(ticket: str, request: Request, claim: bool = False):
    row = get_login_ticket(ticket)
    if not row:
        fail(request, 404, "api.qr_invalid")
    payload = {"status": row["status"], "expires_at": row["expires_at"]}
    if claim and row["status"] == "confirmed":
        user = consume_confirmed_ticket(ticket)
        if user:
            response = JSONResponse({"status": "ok", "user": user})
            set_session(response, create_session(user["id"]), request)
            return response
    if row["status"] == "confirmed" and row.get("user_id"):
        payload["ready"] = True
    return payload


@router.post("/api/auth/qr/{ticket}/confirm")
def api_auth_qr_confirm(ticket: str, request: Request) -> dict:
    user = current_user(request)
    if not user:
        fail(request, 401, "api.need_login")
    try:
        confirm_login_ticket(ticket, user["id"])
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return {"ok": True, "user": user}
