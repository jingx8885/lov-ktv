from __future__ import annotations

from fastapi import APIRouter, Body
from starlette.requests import Request

from lovktv.identity.ads import catalog, click_ad, complete_ad, public_ad, start_ad
from lovktv.identity.points import claim_bonus, points_payload
from lovktv.services.http import fail
from lovktv.storage import settings

router = APIRouter()


@router.get("/api/points")
def api_points(request: Request) -> dict:
    return points_payload(request)


@router.get("/api/ads")
def api_ads(request: Request, placement: str = "splash") -> dict:
    ads = catalog(request)
    picked = ads[0] if placement != "wait" else ads[min(1, len(ads) - 1)]
    return {
        "placement": placement or "splash",
        "ad": public_ad(picked),
        "ads": [public_ad(item) for item in ads],
        "points": points_payload(request),
    }


@router.post("/api/ads/start")
def api_ads_start(request: Request, payload: dict = Body(default={})) -> dict:
    return start_ad(request, str(payload.get("placement") or "wait"))


@router.post("/api/ads/click")
def api_ads_click(request: Request, payload: dict = Body(default={})) -> dict:
    token = str(payload.get("token") or "")
    if not token:
        fail(request, 400, "api.ad_invalid")
    return click_ad(request, token)


@router.post("/api/ads/complete")
def api_ads_complete(request: Request, payload: dict = Body(default={})) -> dict:
    token = str(payload.get("token") or "")
    if not token:
        fail(request, 400, "api.ad_invalid")
    return complete_ad(request, token)


@router.post("/api/points/claim")
def api_points_claim(request: Request, payload: dict = Body(default={})) -> dict:
    kind = str(payload.get("kind") or "")
    if kind != "download":
        fail(request, 400, "api.ad_invalid")
    return claim_bonus(request, "download", settings.get("download_bonus"))
