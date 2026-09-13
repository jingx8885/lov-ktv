"""Commercial billing: Stripe subscriptions and Google Sign-In."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import string
import time

import httpx
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from lovktv.core.config import (
    GOOGLE_CLIENT_ID,
    STRIPE_PRICE_5,
    STRIPE_PRICE_20,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
)
from lovktv.identity.plans import PLAN_LIMITS, PLAN_ROOM_LIMITS, effective_plan
from lovktv.services.http import current_user, request_base, set_session
from lovktv.storage.store import (
    claim_billing_event,
    connect,
    create_session,
    execute,
    update_billing_user,
    upsert_google_user,
)

router = APIRouter()


def _stripe_client():
    """Create an isolated Stripe client for server-side billing calls."""
    from stripe import HTTPXClient, StripeClient

    # Do not inherit LOVKTV_HTTPS_PROXY: Stripe traffic must use the direct
    # egress path, while media providers use the Clash sidecar proxy.
    return StripeClient(
        STRIPE_SECRET_KEY,
        stripe_version="2026-08-26.dahlia",
        http_client=HTTPXClient(timeout=20, allow_sync_methods=True),
    )
PLANS = {
    "starter": {
        "name": "入门包月",
        "price": 5,
        "price_id": STRIPE_PRICE_5,
        "monthly_limit": PLAN_LIMITS["starter"],
        "room_limit": PLAN_ROOM_LIMITS["starter"],
        "features": ["每月 100 首处理额度", "标准音频处理", "1 个房间"],
    },
    "pro": {
        "name": "畅唱包月",
        "price": 20,
        "price_id": STRIPE_PRICE_20,
        "monthly_limit": PLAN_LIMITS["pro"],
        "room_limit": PLAN_ROOM_LIMITS["pro"],
        "features": ["每月 1000 首处理额度", "优先音频处理", "最多 5 个房间"],
    },
}


def _require_user(request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, "请先登录")
    return u


@router.get("/api/billing/plans")
def plans():
    # Price IDs are implementation details; the public contract is stable.
    return {
        "plans": {
            key: {k: value for k, value in plan.items() if k != "price_id"}
            for key, plan in PLANS.items()
        }
    }


@router.get("/api/billing/me")
def billing_me(request: Request):
    user = _require_user(request)
    from lovktv.identity.quota import quota_payload

    return {
        "plan": effective_plan(user),
        "status": user.get("plan_status") or "active",
        "quota": quota_payload(request, user),
    }


@router.post("/api/billing/checkout")
def checkout(request: Request, payload: dict = Body(default={})):
    user = _require_user(request)
    key = str(payload.get("plan") or "starter")
    plan = PLANS.get(key)
    if not plan or not plan["price_id"]:
        raise HTTPException(400, "套餐尚未配置")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "支付服务尚未配置")
    if user.get("stripe_subscription_id") and user.get("plan_status") not in {
        "canceled",
        "expired",
    }:
        raise HTTPException(409, "当前已有有效订阅，请在订阅管理中更换套餐")
    data = {
        "mode": "subscription",
        "line_items": [{"price": plan["price_id"], "quantity": 1}],
        "success_url": request_base(request) + "/billing.html?payment=success",
        "cancel_url": request_base(request) + "/billing.html?payment=cancel",
        "client_reference_id": str(user["id"]),
        "metadata": {"user_id": str(user["id"]), "plan": key},
        "subscription_data": {
            "metadata": {"user_id": str(user["id"]), "plan": key}
        },
        # Stripe recommends an integration identifier on current API versions
        # so Checkout conversion can be compared in the Dashboard.
        "integration_identifier": "lovktv_"
        + "".join(secrets.choice(string.ascii_lowercase) for _ in range(8)),
    }
    if user.get("stripe_customer_id"):
        data["customer"] = str(user["stripe_customer_id"])
    elif user.get("email"):
        data["customer_email"] = str(user["email"])
    idem = f"lovktv-{user['id']}-{key}-{int(time.time() // 60)}"
    from stripe import RequestOptions, StripeError

    try:
        session = _stripe_client().v1.checkout.sessions.create(
            data, options=RequestOptions(idempotency_key=idem)
        )
    except StripeError as exc:
        raise HTTPException(502, "Stripe 创建支付失败：" + str(exc)) from exc
    return {"url": session.url, "session_id": session.id}


@router.post("/api/billing/portal")
def portal(request: Request):
    user = _require_user(request)
    customer = str(user.get("stripe_customer_id") or "")
    if not STRIPE_SECRET_KEY or not customer:
        raise HTTPException(400, "当前账号没有可管理的订阅")
    from stripe import StripeError

    try:
        session = _stripe_client().v1.billing_portal.sessions.create(
            {
                "customer": customer,
                "return_url": request_base(request) + "/billing.html",
            }
        )
    except StripeError as exc:
        raise HTTPException(502, "Stripe 管理页面创建失败") from exc
    return {"url": session.url}


@router.post("/api/billing/webhook")
async def webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if STRIPE_WEBHOOK_SECRET:
        try:
            parts = [item.strip() for item in sig.split(",")]
            ts = int(next(item[2:] for item in parts if item.startswith("t=")))
            signatures = [item[3:] for item in parts if item.startswith("v1=")]
            expected = hmac.new(
                STRIPE_WEBHOOK_SECRET.encode(),
                f"{ts}.".encode() + payload,
                hashlib.sha256,
            ).hexdigest()
            if abs(time.time() - ts) > 300 or not any(
                hmac.compare_digest(expected, got) for got in signatures
            ):
                raise ValueError
        except Exception:
            raise HTTPException(400, "无效 webhook 签名")
    try:
        event = json.loads(payload or b"{}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Webhook JSON 无效") from exc
    event_id = str(event.get("id") or "")
    if event_id and not claim_billing_event(event_id):
        return {"received": True, "duplicate": True}
    typ = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    meta = obj.get("metadata") or {}
    uid = str(obj.get("client_reference_id") or meta.get("user_id") or "")
    if typ in {"checkout.session.completed", "checkout.session.async_payment_succeeded"} and uid:
        payment_status = str(obj.get("payment_status") or "")
        if typ == "checkout.session.completed" and payment_status not in {
            "paid",
            "no_payment_required",
        }:
            return {"received": True, "pending": True}
        plan = str(meta.get("plan") or "starter")
        update_billing_user(
            uid,
            plan=plan if plan in PLANS else "starter",
            plan_status="active",
            stripe_customer_id=obj.get("customer", ""),
            stripe_subscription_id=obj.get("subscription", ""),
        )
    elif typ in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
    ):
        sub = obj.get("id", "")
        with connect() as conn:
            row = execute(
                conn,
                "SELECT id FROM users WHERE stripe_subscription_id=? OR stripe_customer_id=?",
                (sub, str(obj.get("customer") or "")),
            ).fetchone()
        if row or meta.get("user_id"):
            user_id = row["id"] if row else str(meta.get("user_id"))
            status = str(obj.get("status") or "")
            if typ in (
                "customer.subscription.deleted",
                "customer.subscription.paused",
            ) or status in (
                "canceled",
                "unpaid",
                "past_due",
                "incomplete",
                "incomplete_expired",
            ):
                update_billing_user(
                    user_id,
                    plan="free",
                    plan_status="canceled",
                    plan_expires_at=int(obj.get("current_period_end") or 0) * 1000,
                )
            else:
                plan = str((obj.get("metadata") or {}).get("plan") or "starter")
                update_billing_user(
                    user_id,
                    plan=plan if plan in PLANS else "starter",
                    plan_status="active",
                    stripe_customer_id=str(obj.get("customer") or ""),
                    stripe_subscription_id=str(sub),
                    plan_expires_at=int(obj.get("current_period_end") or 0) * 1000,
                )
    elif typ in ("invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"):
        customer = str(obj.get("customer") or "")
        sub = str(obj.get("subscription") or "")
        with connect() as conn:
            row = execute(
                conn,
                "SELECT id FROM users WHERE stripe_subscription_id=? OR stripe_customer_id=?",
                (sub, customer),
            ).fetchone()
        if row:
            if typ == "invoice.payment_failed":
                update_billing_user(row["id"], plan_status="past_due")
            else:
                update_billing_user(row["id"], plan_status="active")
    return {"received": True}


@router.get("/api/auth/google/config")
def google_config():
    return {"client_id": GOOGLE_CLIENT_ID, "enabled": bool(GOOGLE_CLIENT_ID)}


@router.post("/api/auth/google")
def google_login(request: Request, payload: dict = Body(default={})):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google 登录尚未配置")
    token = str(payload.get("credential") or payload.get("id_token") or "")
    if not token:
        raise HTTPException(400, "缺少 Google 凭证")
    with httpx.Client(timeout=10, trust_env=False) as google:
        r = google.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": token},
        )
    if r.status_code >= 400:
        raise HTTPException(401, "Google 凭证无效")
    info = r.json()
    if (
        info.get("aud") != GOOGLE_CLIENT_ID
        or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com")
        or info.get("email_verified") not in ("true", True)
    ):
        raise HTTPException(401, "Google 账号校验失败")
    user = upsert_google_user(
        info.get("sub", ""),
        info.get("email", ""),
        info.get("name", ""),
        info.get("picture", ""),
    )
    resp = JSONResponse({"user": user})
    set_session(resp, create_session(user["id"]), request)
    return resp
