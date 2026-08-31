"""Configured splash / wait ads. Phone can jump to the landing URL."""

from __future__ import annotations

from urllib.parse import urljoin

from lovktv.identity.points import day_start_ms, points_payload, wallet_owner
from lovktv.services.http import fail, request_base
from lovktv.storage import points as store
from lovktv.storage import settings
from lovktv.storage.store import now_ms

AD_MIN_MS = 29_000
PLACEMENTS = ("splash", "wait")
ADS_OPEN = False
# Off until outbound landing jumps are wanted. Set LOVKTV_ADS_OPEN=1 to jump.
def _setting(key: str):
    if key == "ads_open" and ADS_OPEN:
        return True
    return settings.get(key)


def _public(request) -> str:
    return (settings.get("public_url") or request_base(request) or "").rstrip("/")


def catalog(request) -> list[dict]:
    base = _public(request)
    ads: list[dict] = []
    extra = _setting("ads_json")
    if extra:
        import json

        try:
            parsed = json.loads(extra)
            if isinstance(parsed, list):
                ads = [item for item in parsed if isinstance(item, dict) and item.get("id")]
        except json.JSONDecodeError:
            pass
    for ad in ads:
        url = str(ad.get("url") or "")
        if url.startswith("/"):
            ad["url"] = urljoin(base + "/", url.lstrip("/"))
        image = str(ad.get("image") or "")
        if image.startswith("/"):
            ad["image"] = urljoin(base + "/", image.lstrip("/")) if base else image
        ad["seconds"] = _setting("ad_seconds")
        ad["reward"] = _setting("ad_reward")
    return ads


def pick_ad(request, placement: str) -> dict | None:
    ads = catalog(request)
    if not ads:
        return None
    if placement == "splash":
        return ads[0]
    if placement == "wait":
        return ads[min(1, len(ads) - 1)]
    return ads[0]


def public_ad(ad: dict | None, *, open_links: bool | None = None) -> dict | None:
    if not ad:
        return None
    allow = _setting("ads_open") if open_links is None else open_links
    return {
        "id": ad.get("id"),
        "title": ad.get("title") or "",
        "body": ad.get("body") or "",
        "image": ad.get("image") or "",
        "url": (ad.get("url") or "") if allow else "",
        "cta": ad.get("cta") or "",
        "kind": ad.get("kind") or "",
        "seconds": int(ad.get("seconds") or _setting("ad_seconds")),
        "reward": int(ad.get("reward") or _setting("ad_reward")),
        "open": allow,
    }


def start_ad(request, placement: str) -> dict:
    kind = placement if placement in PLACEMENTS else "wait"
    owner = wallet_owner(request)
    if store.completed_ads_today(owner, day_start_ms()) >= _setting("ad_day_limit"):
        fail(request, 429, "api.ad_day_limit")
    ad = pick_ad(request, kind)
    if not ad:
        return {
            "token": "",
            "placement": kind,
            "ad": None,
            "points": points_payload(request),
        }
    session = store.create_ad_session(owner, kind, str(ad["id"]))
    return {
        "token": session["token"],
        "placement": kind,
        "ad": public_ad(ad),
        "points": points_payload(request),
    }


def _session_or_fail(request, token: str) -> dict:
    row = store.get_ad_session(token)
    if not row:
        fail(request, 404, "api.ad_invalid")
    if row["owner"] != wallet_owner(request):
        fail(request, 404, "api.ad_invalid")
    return row


def click_ad(request, token: str) -> dict:
    row = _session_or_fail(request, token)
    store.mark_ad_clicked(token)
    ad = next((item for item in catalog(request) if item["id"] == row["ad_id"]), None)
    url = (ad or {}).get("url") or (pick_ad(request, row["placement"]) or {}).get("url", "")
    if not _setting("ads_open"):
        url = ""
    return {"url": url, "kind": (ad or {}).get("kind") or "", "open": _setting("ads_open")}


def complete_ad(request, token: str) -> dict:
    row = _session_or_fail(request, token)
    if int(row.get("completed_at") or 0) > 0:
        fail(request, 409, "api.ad_done")
    waited = now_ms() - int(row.get("started_at") or 0)
    if waited < AD_MIN_MS:
        fail(request, 400, "api.ad_too_soon")
    if not store.mark_ad_completed(token):
        fail(request, 409, "api.ad_done")
    owner = row["owner"]
    reward = _setting("ad_reward")
    store.apply_delta(owner, "ad", reward, token)
    return {"ok": True, "reward": reward, "points": points_payload(request)}
