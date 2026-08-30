"""Guest song quota. Logged-in accounts are unlimited."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from lovktv.services.http import current_user, fail
from lovktv.services.room_runtime import request_ip
from lovktv.storage import store

GUEST_SONG_LIMIT = 5
_SHANGHAI = timezone(timedelta(hours=8))


def shanghai_day(now_ms: int | None = None) -> str:
    if now_ms is None:
        now_ms = store.now_ms()
    return datetime.fromtimestamp(now_ms / 1000, tz=_SHANGHAI).strftime("%Y-%m-%d")


def is_account(user: dict | None) -> bool:
    return bool(user and user.get("account"))


def guest_key(request, user: dict | None = None) -> str:
    if user and user.get("id") and not is_account(user):
        return "u:" + str(user["id"])
    machine = "".join(
        ch
        for ch in (request.headers.get("x-lovktv-machine") or "")
        if ch.isalnum() or ch in "-_"
    )[:64]
    if len(machine) >= 8:
        return "m:" + machine
    host = (request.cookies.get("lovktv_host") or "").strip()
    if len(host) >= 8:
        return "h:" + host[:64]
    ip = request_ip(request)
    ua = " ".join((request.headers.get("user-agent") or "").split())[:120]
    digest = hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()[:32]
    return "g:" + digest


def quota_payload(request, user: dict | None = None) -> dict:
    user = user if user is not None else current_user(request)
    if is_account(user):
        return {
            "unlimited": True,
            "limit": GUEST_SONG_LIMIT,
            "used": 0,
            "remaining": None,
            "account": True,
        }
    used = store.guest_song_used(guest_key(request, user), shanghai_day())
    remaining = max(0, GUEST_SONG_LIMIT - used)
    return {
        "unlimited": False,
        "limit": GUEST_SONG_LIMIT,
        "used": used,
        "remaining": remaining,
        "account": False,
    }


def consume_guest_song(request) -> dict:
    user = current_user(request)
    quota = quota_payload(request, user)
    if quota["unlimited"]:
        return quota
    if quota["remaining"] <= 0:
        fail(request, 429, "api.guest_limit", limit=GUEST_SONG_LIMIT)
    store.increment_guest_song(guest_key(request, user), shanghai_day())
    return quota_payload(request, user)
