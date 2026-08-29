from __future__ import annotations

from fastapi import WebSocket

from lovktv.i18n import localize_song
from lovktv.room_service import RoomCommand, room_service
from lovktv.room_store import remember_host_room
from lovktv.store import host_keys, with_media_flags
from lovktv import store
from lovktv.runtime import _mics, _peers, _rooms, host_volume_meta, set_host_volume


def room_view(code: str, snap: dict | None = None, lang: str = "zh") -> dict:
    room = dict(snap or room_service.snapshot(code))
    room["mic_on"] = bool(_mics.get(code))
    room["mic_peer"] = _mics.get(code) or ""
    room.update(host_volume_meta())
    if room.get("now_playing"):
        room["now_playing"] = localize_song(lang, with_media_flags(room["now_playing"]))
    room["queue"] = [localize_song(lang, with_media_flags(item) or item) for item in room.get("queue") or []]
    room["paused"] = bool(int(room.get("paused") or 0))
    return room


async def broadcast(code: str, payload: dict, skip: WebSocket | None = None) -> None:
    for peer in list(_rooms.get(code, set())):
        if peer is skip:
            continue
        try:
            await peer.send_json(payload)
        except Exception:
            _rooms.get(code, set()).discard(peer)
            _peers.pop(peer, None)


def run_command(code: str, command: RoomCommand) -> dict:
    snap = room_service.execute(code, command)
    if command.volume is not None:
        set_host_volume(int(command.volume or 0))
    return snap


def host_machine(request) -> str:
    cookie = (request.cookies.get("lovktv_host") or "").strip()
    header = (request.headers.get("x-lovktv-machine") or "").strip()
    mid = cookie or header
    return "".join(ch for ch in mid if ch.isalnum() or ch in "-_")[:64]


def request_ip(request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        raw = (request.headers.get(header) or "").strip()
        if raw:
            return raw.split(",")[0].strip()
    return request.client.host if request.client else ""


def host_keys_for(request) -> list[str]:
    return host_keys(host_machine(request), request.headers.get("user-agent") or "", request_ip(request))


def bind_host(request, room: str) -> str:
    machine = host_machine(request)
    token = machine if len(machine) >= 8 else store.new_id()
    keys = host_keys(token, request.headers.get("user-agent") or "", request_ip(request))
    remember_host_room(keys, room, request.headers.get("user-agent") or "")
    return token
