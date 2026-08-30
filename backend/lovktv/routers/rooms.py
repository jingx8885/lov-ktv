from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.requests import Request

from lovktv.api.models import RoomCommandPayload, RoomLanPayload
from lovktv.domain.room_contract import normalize_playback_event
from lovktv.identity.points import charge_queue
from lovktv.locale.i18n import (
    localize_error_text,
    localize_exc,
    request_lang,
    translate,
    ws_lang,
)
from lovktv.platform.runtime import _mics, _peers, _rooms
from lovktv.rooms.service import RoomCommand, room_service
from lovktv.services.http import fail, set_host_cookie
from lovktv.services.room_runtime import (
    bind_host,
    broadcast,
    host_machine,
    request_ip,
    room_view,
    run_command,
)
from lovktv.storage import store
from lovktv.storage.room_store import ensure_room_for_host, room_for_hosts, set_room_lan
from lovktv.storage.store import get_song, host_keys

router = APIRouter()


@router.get("/api/rooms")
def api_my_room(request: Request) -> dict:
    code = room_for_hosts(
        host_keys(
            host_machine(request),
            request.headers.get("user-agent") or "",
            request_ip(request),
        )
    )
    return {"code": ""} if not code else room_view(code, lang=request_lang(request))


@router.post("/api/rooms")
def api_create_room(request: Request) -> JSONResponse:
    ua = request.headers.get("user-agent") or ""
    machine = host_machine(request)
    token = machine if len(machine) >= 8 else store.new_id()
    room = ensure_room_for_host(host_keys(token, ua, request_ip(request)), ua)
    return set_host_cookie(
        JSONResponse(room_view(room["code"], lang=request_lang(request))),
        request,
        token,
    )


@router.get("/api/rooms/{code}")
def api_room(request: Request, code: str) -> JSONResponse:
    code = code.upper()
    view = room_view(code, lang=request_lang(request))
    return set_host_cookie(
        JSONResponse(view), request, bind_host(request, view["code"])
    )


@router.post("/api/rooms/{code}/lan")
def api_room_lan(request: Request, code: str, payload: RoomLanPayload) -> JSONResponse:
    code = code.upper()
    try:
        snap = set_room_lan(
            code, payload.origin_url(), payload.mic_port, payload.mic_sample_rate
        )
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return set_host_cookie(
        JSONResponse(room_view(code, snap, lang=request_lang(request))),
        request,
        bind_host(request, snap["code"]),
    )


@router.post("/api/rooms/{code}/queue")
async def api_enqueue(request: Request, code: str, payload: RoomCommandPayload) -> dict:
    code = code.upper()
    song_id = str(payload.song_id or "")
    if not get_song(song_id):
        fail(request, 404, "api.song_not_found")
    queued = {item.get("song_id") for item in room_service.snapshot(code).get("queue") or []}
    if song_id not in queued:
        charge_queue(request, song_id)
    try:
        snap = run_command(code, RoomCommand.from_payload("enqueue", payload.as_dict()))
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    view = room_view(code, snap, lang=request_lang(request))
    await broadcast(code, {"type": "snapshot", "room": view})
    return view


@router.post("/api/rooms/{code}/bump")
def api_bump(code: str, payload: RoomCommandPayload) -> dict:
    return run_command(
        code.upper(), RoomCommand.from_payload("bump", payload.as_dict())
    )


@router.post("/api/rooms/{code}/skip")
async def api_skip(request: Request, code: str) -> dict:
    code = code.upper()
    view = room_view(
        code,
        run_command(code, RoomCommand.from_payload("skip")),
        lang=request_lang(request),
    )
    await broadcast(code, {"type": "snapshot", "room": view})
    return view


@router.post("/api/rooms/{code}/play")
async def api_play(request: Request, code: str, payload: RoomCommandPayload) -> dict:
    code = code.upper()
    try:
        snap = run_command(code, RoomCommand.from_payload("play", payload.as_dict()))
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    view = room_view(code, snap, lang=request_lang(request))
    await broadcast(code, {"type": "snapshot", "room": view})
    return view


@router.post("/api/rooms/{code}/mix")
async def api_mix(request: Request, code: str, payload: RoomCommandPayload) -> dict:
    code = code.upper()
    snap = run_command(code, RoomCommand.from_payload("mix", payload.as_dict()))
    view = room_view(code, snap, lang=request_lang(request))
    await broadcast(code, {"type": "snapshot", "room": view})
    return view


@router.websocket("/ws/rooms/{code}")
async def ws_room(ws: WebSocket, code: str) -> None:
    code = code.upper()
    lang = ws_lang(ws)
    await ws.accept()
    _rooms.setdefault(code, set()).add(ws)
    _peers[ws] = {"code": code, "peer": "", "role": ""}
    await ws.send_json({"type": "snapshot", "room": room_view(code, lang=lang)})
    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            if action == "hello":
                _peers[ws] = {
                    "code": code,
                    "peer": str(msg.get("peer") or ""),
                    "role": str(msg.get("role") or ""),
                }
                await broadcast(
                    code,
                    {
                        "type": "peer",
                        "event": "join",
                        "peer": _peers[ws]["peer"],
                        "role": _peers[ws]["role"],
                    },
                    skip=ws,
                )
                continue
            if action == "rtc":
                kind = str(msg.get("kind") or "")
                peer = str(msg.get("from") or _peers.get(ws, {}).get("peer") or "")
                if kind == "offer" and peer:
                    _mics[code] = peer
                if kind == "hangup" and _mics.get(code) == peer:
                    _mics.pop(code, None)
                await broadcast(
                    code,
                    {"type": "rtc", **{k: v for k, v in msg.items() if k != "action"}},
                    skip=ws,
                )
                if kind in {"offer", "hangup"}:
                    await broadcast(
                        code, {"type": "snapshot", "room": room_view(code, lang=lang)}
                    )
                continue
            if action == "mic":
                peer = str(msg.get("from") or _peers.get(ws, {}).get("peer") or "")
                if msg.get("on") and peer:
                    _mics[code] = peer
                elif _mics.get(code) == peer or not peer:
                    _mics.pop(code, None)
                if msg.get("mic_gain") is not None:
                    run_command(
                        code,
                        RoomCommand.from_payload(
                            "mix", {"mic_gain": msg.get("mic_gain")}
                        ),
                    )
                await broadcast(
                    code, {"type": "snapshot", "room": room_view(code, lang=lang)}
                )
                continue
            try:
                if action in {"skip", "bump", "play"}:
                    event = normalize_playback_event(action, msg)
                    snap = run_command(
                        code, RoomCommand.from_payload(event["action"], event)
                    )
                elif action == "enqueue":
                    song_id = str(msg.get("song_id") or "")
                    queued = {
                        item.get("song_id")
                        for item in room_service.snapshot(code).get("queue") or []
                    }
                    if song_id and song_id not in queued:
                        try:
                            charge_queue(ws, song_id)
                        except HTTPException as exc:
                            await ws.send_json(
                                {
                                    "type": "error",
                                    "message": str(exc.detail),
                                }
                            )
                            continue
                    snap = run_command(code, RoomCommand.from_payload("enqueue", msg))
                elif action == "mix":
                    snap = run_command(code, RoomCommand.from_payload("mix", msg))
                else:
                    await ws.send_json(
                        {
                            "type": "error",
                            "message": translate(lang, "api.unknown_command"),
                        }
                    )
                    continue
            except ValueError as exc:
                await ws.send_json(
                    {"type": "error", "message": localize_error_text(lang, str(exc))}
                )
                continue
            await broadcast(
                code, {"type": "snapshot", "room": room_view(code, snap, lang=lang)}
            )
    except WebSocketDisconnect:
        info = _peers.pop(ws, {})
        _rooms.get(code, set()).discard(ws)
        peer = str(info.get("peer") or "")
        if peer and _mics.get(code) == peer:
            _mics.pop(code, None)
            await broadcast(code, {"type": "rtc", "kind": "hangup", "from": peer})
            await broadcast(
                code, {"type": "snapshot", "room": room_view(code, lang=lang)}
            )
        await broadcast(
            code,
            {
                "type": "peer",
                "event": "leave",
                "peer": peer,
                "role": info.get("role") or "",
            },
        )
