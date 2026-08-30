"""First-party splash / wait ads. Phone can jump to the landing URL."""

from __future__ import annotations

import os
from urllib.parse import urljoin

from lovktv.core.config import PUBLIC_URL
from lovktv.identity.points import (
    AD_DAY_LIMIT,
    AD_REWARD,
    AD_SECONDS,
    day_start_ms,
    points_payload,
    wallet_owner,
)
from lovktv.services.http import fail, request_base
from lovktv.storage import points as store
from lovktv.storage.store import now_ms

AD_MIN_MS = 29_000
PLACEMENTS = ("splash", "wait")


def _public(request) -> str:
    return (PUBLIC_URL or request_base(request) or "").rstrip("/")


def catalog(request) -> list[dict]:
    base = _public(request)
    phone = f"{base}/apps/phone.apk" if base else "/apps/phone.apk"
    tv = f"{base}/apps/tv.apk" if base else "/apps/tv.apk"
    login = f"{base}/login.html" if base else "/login.html"
    ads = [
        {
            "id": "phone-app",
            "title": "lov-ktv 手机点歌",
            "body": "装上手机 App，扫码进房。下载送 10 积分。",
            "image": "/brand/apple-touch.png",
            "url": phone,
            "cta": "下载手机 App",
            "kind": "download",
        },
        {
            "id": "tv-app",
            "title": "电视盒子也能唱",
            "body": "装上电视 App，客厅直接开包厢。",
            "image": "/brand/icon.png",
            "url": tv,
            "cta": "下载电视 App",
            "kind": "download",
        },
        {
            "id": "register",
            "title": "注册送 10 积分",
            "body": "写个用户名和密码就能进。处理一首歌 5 积分，点歌 1 积分。",
            "image": "/brand/icon.png",
            "url": login,
            "cta": "去注册",
            "kind": "register",
        },
    ]
    extra = (os.environ.get("LOVKTV_ADS_JSON") or "").strip()
    if extra:
        import json

        try:
            parsed = json.loads(extra)
            if isinstance(parsed, list) and parsed:
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
        ad["seconds"] = AD_SECONDS
        ad["reward"] = AD_REWARD
    return ads


def pick_ad(request, placement: str) -> dict:
    ads = catalog(request)
    if placement == "splash":
        return ads[0]
    if placement == "wait":
        return ads[min(1, len(ads) - 1)]
    return ads[0]


def public_ad(ad: dict) -> dict:
    return {
        "id": ad.get("id"),
        "title": ad.get("title") or "",
        "body": ad.get("body") or "",
        "image": ad.get("image") or "",
        "url": ad.get("url") or "",
        "cta": ad.get("cta") or "",
        "kind": ad.get("kind") or "",
        "seconds": int(ad.get("seconds") or AD_SECONDS),
        "reward": int(ad.get("reward") or AD_REWARD),
    }


def start_ad(request, placement: str) -> dict:
    kind = placement if placement in PLACEMENTS else "wait"
    owner = wallet_owner(request)
    if store.completed_ads_today(owner, day_start_ms()) >= AD_DAY_LIMIT:
        fail(request, 429, "api.ad_day_limit")
    ad = pick_ad(request, kind)
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
    url = (ad or {}).get("url") or pick_ad(request, row["placement"])["url"]
    return {"url": url, "kind": (ad or {}).get("kind") or ""}


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
    store.apply_delta(owner, "ad", AD_REWARD, token)
    return {"ok": True, "reward": AD_REWARD, "points": points_payload(request)}
