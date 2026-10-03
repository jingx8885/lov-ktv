"""Tiny first-party funnel telemetry. Server-side events only, no cookies,
no fingerprinting: owner is the same opaque key the quota system already uses."""

from __future__ import annotations

import json

from lovktv.storage import store

FUNNEL_KINDS = frozenset(
    {
        "landing_view",
        "cta_tv",
        "cta_phone",
        "song_search",
        "song_queued",
        "signup",
        "login",
        "checkout_start",
        "paid",
        "sub_status",
    }
)


def _dump_meta(meta: dict | None) -> str:
    if not meta:
        return ""
    try:
        return json.dumps({k: str(v)[:200] for k, v in meta.items()}, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def track(request, kind: str, meta: dict | None = None) -> None:
    """Best-effort event insert keyed by the caller's owner. Never raises:
    telemetry must not break product flows."""
    try:
        if kind not in FUNNEL_KINDS:
            return
        owner = ""
        try:
            from lovktv.services.http import current_user

            user = current_user(request)
            if user and user.get("id"):
                owner = "u:" + str(user["id"])
            else:
                from lovktv.identity.quota import guest_key

                owner = guest_key(request, user)
        except Exception:
            owner = ""
        store.track_funnel_event(kind, owner, _dump_meta(meta))
    except Exception:
        pass


def track_owner(kind: str, owner: str, meta: dict | None = None) -> None:
    """Event variant for contexts without a request (e.g. Stripe webhooks)."""
    try:
        if kind not in FUNNEL_KINDS:
            return
        store.track_funnel_event(kind, str(owner or ""), _dump_meta(meta))
    except Exception:
        pass
