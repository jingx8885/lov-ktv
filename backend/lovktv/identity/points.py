"""Spend and earn points for queue / process / ads / bonuses."""

from __future__ import annotations

import os

from lovktv.identity.quota import guest_key, is_account, quota_payload
from lovktv.services.http import current_user, fail
from lovktv.storage import points as store

QUEUE_COST = 1
PROCESS_COST = 5
AD_REWARD = 1
AD_SECONDS = 30
REGISTER_BONUS = 10
DOWNLOAD_BONUS = 10
AD_DAY_LIMIT = 40
# Off until the admin/recharge flow is in daily use. Set LOVKTV_POINTS=1 to charge.
POINTS_ENFORCED = (os.environ.get("LOVKTV_POINTS") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def wallet_owner(request, user: dict | None = None) -> str:
    user = user if user is not None else current_user(request)
    if user and user.get("id"):
        return "u:" + str(user["id"])
    return guest_key(request, user)


def points_payload(request, user: dict | None = None) -> dict:
    owner = wallet_owner(request, user)
    return {
        "balance": store.wallet_balance(owner),
        "queue_cost": QUEUE_COST,
        "process_cost": PROCESS_COST,
        "ad_reward": AD_REWARD,
        "ad_seconds": AD_SECONDS,
        "register_bonus": REGISTER_BONUS,
        "download_bonus": DOWNLOAD_BONUS,
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
        store.apply_delta(dest, "register", REGISTER_BONUS, "register")
    return points_payload(request, user)


def charge_process(request) -> dict:
    if not POINTS_ENFORCED:
        return {"free": True, "skipped": True, "points": points_payload(request)}
    user = current_user(request)
    if not is_account(user):
        quota = quota_payload(request, user)
        if quota["remaining"] > 0:
            from lovktv.identity.quota import consume_guest_song

            return {"free": True, "quota": consume_guest_song(request)}
    return {"free": False, "points": spend(request, PROCESS_COST, "process")}


def charge_queue(request, song_id: str = "") -> dict:
    if not POINTS_ENFORCED:
        return points_payload(request)
    return spend(request, QUEUE_COST, "queue", song_id)


def day_start_ms() -> int:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone(timedelta(hours=8)))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)
