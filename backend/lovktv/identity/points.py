"""Spend and earn points for queue / process / ads / bonuses."""

from __future__ import annotations

from lovktv.identity.quota import guest_key, is_account, quota_payload
from lovktv.services.http import current_user, fail
from lovktv.storage import points as store
from lovktv.storage import settings

QUEUE_COST = 1
PROCESS_COST = 5
AD_REWARD = 1
AD_SECONDS = 30
REGISTER_BONUS = 10
DOWNLOAD_BONUS = 10
AD_DAY_LIMIT = 40
POINTS_ENFORCED = False

def _setting(key: str):
    if key == "points_enabled" and POINTS_ENFORCED:
        return True
    return settings.get(key)


def wallet_owner(request, user: dict | None = None) -> str:
    user = user if user is not None else current_user(request)
    if user and user.get("id"):
        return "u:" + str(user["id"])
    return guest_key(request, user)


def points_payload(request, user: dict | None = None) -> dict:
    owner = wallet_owner(request, user)
    return {
        "balance": store.wallet_balance(owner),
        "queue_cost": _setting("queue_cost"),
        "process_cost": _setting("process_cost"),
        "ad_reward": _setting("ad_reward"),
        "ad_seconds": _setting("ad_seconds"),
        "register_bonus": _setting("register_bonus"),
        "download_bonus": _setting("download_bonus"),
    }


def spend(request, amount: int, kind: str, ref: str = "") -> dict:
    owner = wallet_owner(request)
    have = store.wallet_balance(owner)
    if have < amount:
        fail(request, 402, "api.need_points", cost=amount, have=have)
    store.apply_delta(owner, kind, -amount, ref)
    return points_payload(request)


def credit(request, amount: int, kind: str, ref: str = "") -> dict:
    owner = wallet_owner(request)
    store.apply_delta(owner, kind, amount, ref)
    return points_payload(request)


def claim_bonus(request, kind: str, amount: int) -> dict:
    owner = wallet_owner(request)
    if not store.add_claim(owner, kind):
        fail(request, 409, "api.points_claimed")
    store.apply_delta(owner, kind, amount, kind)
    return points_payload(request)


def grant_register(request, user: dict) -> dict:
    dest = "u:" + str(user["id"])
    src = guest_key(request, None)
    if src and src != dest:
        store.merge_wallets(src, dest)
    if store.add_claim(dest, "register"):
        store.apply_delta(dest, "register", _setting("register_bonus"), "register")
    return points_payload(request, user)


def charge_process(request) -> dict:
    if not _setting("points_enabled"):
        return {"free": True, "skipped": True, "points": points_payload(request)}
    user = current_user(request)
    if not is_account(user):
        quota = quota_payload(request, user)
        if quota["remaining"] > 0:
            from lovktv.identity.quota import consume_guest_song

            return {"free": True, "quota": consume_guest_song(request)}
    return {"free": False, "points": spend(request, _setting("process_cost"), "process")}


def charge_queue(request, song_id: str = "") -> dict:
    if not _setting("points_enabled"):
        return points_payload(request)
    return spend(request, _setting("queue_cost"), "queue", song_id)


def day_start_ms() -> int:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone(timedelta(hours=8)))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)
