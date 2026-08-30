from __future__ import annotations

import hmac

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from lovktv.catalog.mugen import is_mugen_kid
from lovktv.identity.admin import (
    admin_token,
    clear_admin_cookie,
    require_admin,
    set_admin_cookie,
)
from lovktv.identity.ads import catalog, public_ad
from lovktv.identity.points import (
    AD_DAY_LIMIT,
    AD_REWARD,
    AD_SECONDS,
    DOWNLOAD_BONUS,
    PROCESS_COST,
    QUEUE_COST,
    REGISTER_BONUS,
)
from lovktv.locale.i18n import localize_exc
from lovktv.rooms.service import RoomCommand
from lovktv.services.http import fail
from lovktv.services.room_runtime import room_view, run_command
from lovktv.storage import points as point_store
from lovktv.storage.room_store import (
    clear_queue,
    delete_room,
    ensure_room,
    list_rooms,
    remove_queue_item,
    room_exists,
    room_snapshot,
)
from lovktv.storage.store import (
    create_song,
    delete_song,
    get_song,
    get_user,
    get_user_by_username,
    list_songs,
    list_users,
    register_password_user,
    retry_query,
    update_password_user,
    update_song,
    with_media_flags,
)
from lovktv.workers.jobs import process_import, spawn

router = APIRouter()


def _owner_from_user(user: dict) -> str:
    return "u:" + str(user["id"])


def _resolve_owner(payload: dict | None = None, owner: str = "") -> str:
    raw = str(owner or (payload or {}).get("owner") or "").strip()
    username = str((payload or {}).get("username") or "").strip()
    if raw.startswith(("u:", "m:", "h:", "g:")):
        return raw
    if raw:
        public = get_user(raw)
        if public:
            return _owner_from_user(public)
        row = get_user_by_username(raw)
        if row:
            return "u:" + str(row["id"])
        if len(raw) == 6:
            match = next(
                (item for item in list_users(raw, limit=8) if item.get("sid") == raw.upper()),
                None,
            )
            if match:
                return _owner_from_user(match)
    if username:
        row = get_user_by_username(username)
        if row:
            return "u:" + str(row["id"])
    return raw


def _account_payload(owner: str) -> dict:
    balance = point_store.wallet_balance(owner)
    user = None
    if owner.startswith("u:"):
        user = get_user(owner[2:])
    return {
        "owner": owner,
        "balance": balance,
        "user": user,
        "guest": not bool(user),
        "ledger": point_store.list_ledger(owner, limit=40),
    }


@router.post("/api/admin/login")
def api_admin_login(request: Request, payload: dict = Body(default={})) -> JSONResponse:
    expected = admin_token()
    if not expected:
        fail(request, 503, "api.admin_not_configured")
    given = str(payload.get("token") or "").strip()
    if not given:
        auth = request.headers.get("authorization") or ""
        given = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not given or not hmac.compare_digest(given, expected):
        fail(request, 401, "api.admin_unauthorized")
    response = JSONResponse({"ok": True})
    set_admin_cookie(response, request, given)
    return response


@router.post("/api/admin/logout")
def api_admin_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    clear_admin_cookie(response)
    return response


@router.get("/api/admin/me")
def api_admin_me(request: Request) -> dict:
    require_admin(request)
    return {"ok": True}


@router.get("/api/admin/summary")
def api_admin_summary(request: Request) -> dict:
    require_admin(request)
    return {
        "users": len(list_users(limit=200)),
        "songs": len(list_songs()),
        "rooms": len(list_rooms(limit=200)),
        "wallets": len(point_store.list_wallets(limit=200)),
        "points_total": point_store.points_total(),
        "rules": {
            "queue_cost": QUEUE_COST,
            "process_cost": PROCESS_COST,
            "ad_reward": AD_REWARD,
            "ad_seconds": AD_SECONDS,
            "register_bonus": REGISTER_BONUS,
            "download_bonus": DOWNLOAD_BONUS,
            "ad_day_limit": AD_DAY_LIMIT,
        },
    }


def _user_item(user: dict) -> dict:
    owner = _owner_from_user(user)
    return {**user, "owner": owner, "balance": point_store.wallet_balance(owner)}


@router.get("/api/admin/users")
def api_admin_users(request: Request, q: str = "", limit: int = 80) -> dict:
    require_admin(request)
    return {"users": [_user_item(user) for user in list_users(q, limit=limit)]}


@router.post("/api/admin/users")
def api_admin_create_user(request: Request, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    try:
        user = register_password_user(
            str(payload.get("username") or ""), str(payload.get("password") or "")
        )
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    nickname = str(payload.get("nickname") or "").strip()
    if nickname:
        user = update_password_user(user["id"], nickname=nickname)
    return _user_item(user)


@router.post("/api/admin/users/{user_id}")
def api_admin_update_user(
    request: Request, user_id: str, payload: dict = Body(default={})
) -> dict:
    require_admin(request)
    if not get_user(user_id):
        fail(request, 404, "api.admin_need_owner")
    try:
        user = update_password_user(
            user_id,
            nickname=str(payload.get("nickname") or ""),
            password=str(payload.get("password") or ""),
        )
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return _user_item(user)


@router.get("/api/admin/points")
def api_admin_points(request: Request, q: str = "", owner: str = "") -> dict:
    require_admin(request)
    target = _resolve_owner({"owner": owner or q, "username": q})
    wallets = point_store.list_wallets(limit=80)
    enriched = []
    for row in wallets:
        item = dict(row)
        if item["owner"].startswith("u:"):
            item["user"] = get_user(item["owner"][2:])
        enriched.append(item)
    payload = {"wallets": enriched, "ledger": point_store.list_ledger(limit=40)}
    if target:
        payload["account"] = _account_payload(target)
    return payload


@router.post("/api/admin/points")
def api_admin_adjust(request: Request, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    owner = _resolve_owner(payload)
    if not owner:
        fail(request, 400, "api.admin_need_owner")
    try:
        delta = int(payload.get("delta") or 0)
    except (TypeError, ValueError):
        fail(request, 400, "api.admin_bad_delta")
    if delta == 0:
        fail(request, 400, "api.admin_bad_delta")
    note = str(payload.get("note") or "").strip()[:80] or ("管理扣分" if delta < 0 else "管理加分")
    try:
        point_store.apply_delta(owner, "admin", delta, note)
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return _account_payload(owner)


@router.get("/api/admin/recharges")
def api_admin_recharges(request: Request, q: str = "") -> dict:
    require_admin(request)
    owner = _resolve_owner({"owner": q, "username": q}) if q else ""
    rows = point_store.list_ledger(owner=owner if q else "", kind="recharge", limit=80)
    items = []
    for row in rows:
        item = dict(row)
        if item["owner"].startswith("u:"):
            item["user"] = get_user(item["owner"][2:])
        items.append(item)
    account = _account_payload(owner) if owner else None
    return {"recharges": items, "account": account}


@router.post("/api/admin/recharge")
def api_admin_recharge(request: Request, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    owner = _resolve_owner(payload)
    if not owner:
        fail(request, 400, "api.admin_need_owner")
    try:
        amount = int(payload.get("amount") or payload.get("delta") or 0)
    except (TypeError, ValueError):
        fail(request, 400, "api.admin_bad_delta")
    if amount <= 0:
        fail(request, 400, "api.admin_bad_delta")
    note = str(payload.get("note") or "").strip()[:80] or "充值"
    point_store.apply_delta(owner, "recharge", amount, note)
    return _account_payload(owner)


@router.get("/api/admin/songs")
def api_admin_songs(request: Request, q: str = "") -> dict:
    require_admin(request)
    needle = str(q or "").strip().casefold()
    songs = []
    for song in list_songs():
        item = with_media_flags(song) or song
        if needle:
            blob = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("artist") or ""),
                    str(item.get("id") or ""),
                    str(item.get("status") or ""),
                ]
            ).casefold()
            if needle not in blob:
                continue
        songs.append(item)
        if len(songs) >= 120:
            break
    return {"songs": songs}


@router.delete("/api/admin/songs/{song_id}")
def api_admin_delete_song(request: Request, song_id: str) -> dict:
    require_admin(request)
    if not get_song(song_id) or not delete_song(song_id):
        fail(request, 404, "api.song_not_found")
    return {"ok": True, "song_id": song_id}


@router.post("/api/admin/songs/{song_id}/retry")
def api_admin_retry_song(request: Request, song_id: str) -> dict:
    require_admin(request)
    song = get_song(song_id)
    if not song:
        fail(request, 404, "api.song_not_found")
    update_song(song_id, status="queued", error="")
    spawn(
        process_import,
        song_id,
        retry_query(song),
        str(song.get("netease_id") or ""),
        song.get("language"),
    )
    return {"ok": True, "song_id": song_id, "status": "queued"}


@router.post("/api/admin/songs/import")
def api_admin_import(request: Request, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    query = str(payload.get("query") or payload.get("title") or "").strip()
    if not query:
        fail(request, 400, "api.missing_query")
    raw_id = str(payload.get("id") or "")
    language = str(payload.get("language") or ("ja" if is_mugen_kid(raw_id) else "zh"))
    song = create_song(
        title=str(payload.get("title") or query),
        artist=str(payload.get("artist") or ""),
        language=language,
        netease_id=raw_id,
    )
    spawn(process_import, song["id"], query, raw_id, language)
    return with_media_flags(song) or song


@router.post("/api/admin/songs/{song_id}")
def api_admin_edit_song(
    request: Request, song_id: str, payload: dict = Body(default={})
) -> dict:
    require_admin(request)
    if not get_song(song_id):
        fail(request, 404, "api.song_not_found")
    fields = {}
    if "title" in payload:
        fields["title"] = str(payload.get("title") or "").strip()
    if "artist" in payload:
        fields["artist"] = str(payload.get("artist") or "").strip()
    if "language" in payload:
        fields["language"] = str(payload.get("language") or "").strip() or "zh"
    if fields:
        update_song(song_id, **fields)
    song = get_song(song_id)
    return with_media_flags(song) or song or {"id": song_id}


@router.get("/api/admin/rooms")
def api_admin_rooms(request: Request, q: str = "") -> dict:
    require_admin(request)
    needle = str(q or "").strip().upper()
    rooms = list_rooms(limit=80)
    if needle:
        rooms = [room for room in rooms if needle in str(room.get("code") or "")]
    return {"rooms": rooms}


@router.post("/api/admin/rooms")
def api_admin_create_room(request: Request, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    code = str(payload.get("code") or "").strip().upper()
    room = ensure_room(code or None)
    return room_view(room["code"])


@router.get("/api/admin/rooms/{code}")
def api_admin_room(request: Request, code: str) -> dict:
    require_admin(request)
    code = code.upper()
    if not room_exists(code):
        fail(request, 404, "api.room_not_found")
    return room_view(code, room_snapshot(code))


@router.delete("/api/admin/rooms/{code}")
def api_admin_delete_room(request: Request, code: str) -> dict:
    require_admin(request)
    if not delete_room(code):
        fail(request, 404, "api.room_not_found")
    return {"ok": True, "code": code.upper()}


@router.post("/api/admin/rooms/{code}/skip")
def api_admin_skip(request: Request, code: str) -> dict:
    require_admin(request)
    snap = run_command(code.upper(), RoomCommand.from_payload("skip"))
    return room_view(code.upper(), snap)


@router.post("/api/admin/rooms/{code}/clear")
def api_admin_clear(request: Request, code: str) -> dict:
    require_admin(request)
    return room_view(code.upper(), clear_queue(code.upper()))


@router.post("/api/admin/rooms/{code}/queue")
def api_admin_enqueue(request: Request, code: str, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    try:
        snap = run_command(
            code.upper(), RoomCommand.from_payload("enqueue", payload)
        )
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return room_view(code.upper(), snap)


@router.post("/api/admin/rooms/{code}/bump")
def api_admin_bump(request: Request, code: str, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    snap = run_command(code.upper(), RoomCommand.from_payload("bump", payload))
    return room_view(code.upper(), snap)


@router.post("/api/admin/rooms/{code}/play")
def api_admin_play(request: Request, code: str, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    try:
        snap = run_command(code.upper(), RoomCommand.from_payload("play", payload))
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return room_view(code.upper(), snap)


@router.post("/api/admin/rooms/{code}/mix")
def api_admin_mix(request: Request, code: str, payload: dict = Body(default={})) -> dict:
    require_admin(request)
    snap = run_command(code.upper(), RoomCommand.from_payload("mix", payload))
    return room_view(code.upper(), snap)


@router.delete("/api/admin/rooms/{code}/queue/{item_id}")
def api_admin_remove_item(request: Request, code: str, item_id: str) -> dict:
    require_admin(request)
    return room_view(code.upper(), remove_queue_item(code.upper(), item_id))


@router.get("/api/admin/ads")
def api_admin_ads(request: Request) -> dict:
    require_admin(request)
    return {"ads": [public_ad(item) for item in catalog(request)]}
