"""Product entitlements shared by billing, quota and presentation layers."""

from __future__ import annotations

from lovktv.identity.song_admin import is_unrestricted_admin

PLAN_LIMITS = {"free": None, "starter": 100, "pro": 1000, "admin": None}
PLAN_ROOM_LIMITS = {"free": 1, "starter": 1, "pro": 5, "admin": None}


def effective_plan(user: dict | None) -> str:
    if is_unrestricted_admin(user):
        return "admin"
    plan = str((user or {}).get("plan") or "free")
    status = str((user or {}).get("plan_status") or "active")
    if plan not in PLAN_LIMITS or (
        plan in {"starter", "pro"} and status not in {"active", "trialing"}
    ):
        return "free"
    return plan


def processing_priority(user: dict | None) -> int:
    """Higher paid tiers are scheduled ahead of free work."""
    return {"admin": 30, "pro": 20, "starter": 10}.get(effective_plan(user), 0)
