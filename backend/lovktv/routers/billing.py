"""Commercial billing: Stripe subscriptions and Google Sign-In."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import pathlib
import secrets
import string
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from lovktv.core.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_PLAY_PACKAGE,
    GOOGLE_PLAY_SERVICE_ACCOUNT_FILE,
    GOOGLE_PLAY_SERVICE_ACCOUNT_JSON,
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

PLAY_PRODUCTS = {
    "starter_monthly": "starter",
    "pro_monthly": "pro",
}


def _play_service_account() -> dict:
    raw = GOOGLE_PLAY_SERVICE_ACCOUNT_JSON
    if not raw and GOOGLE_PLAY_SERVICE_ACCOUNT_FILE:
        raw = pathlib.Path(GOOGLE_PLAY_SERVICE_ACCOUNT_FILE).read_text(encoding="utf-8")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = json.loads(base64.b64decode(raw).decode("utf-8"))
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def _play_access_token(account: dict) -> str:
    """Mint a short-lived Google OAuth token without a heavyweight SDK."""
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA
    from Crypto.Signature import pkcs1_15

    if not account.get("client_email") or not account.get("private_key"):
        raise HTTPException(503, "Google Play 服务账号配置不完整")
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claim = {
        "iss": account["client_email"],
        "scope": "https://www.googleapis.com/auth/androidpublisher",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    enc = lambda obj: base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    unsigned = f"{enc(header)}.{enc(claim)}"
    signature = pkcs1_15.new(RSA.import_key(account["private_key"])).sign(
        SHA256.new(unsigned.encode())
    )
    assertion = unsigned + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
    response.raise_for_status()
    return str(response.json().get("access_token") or "")


def _verify_play_purchase(product_id: str, purchase_token: str) -> dict:
    account = _play_service_account()
    if not account or not GOOGLE_PLAY_PACKAGE:
        raise HTTPException(503, "Google Play 验证尚未配置")
    if product_id not in PLAY_PRODUCTS or not purchase_token:
        raise HTTPException(400, "Google Play 购买信息无效")
    token = _play_access_token(account)
    url = (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
        f"{GOOGLE_PLAY_PACKAGE}/purchases/subscriptionsv2/tokens/{purchase_token}"
    )
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.get(url, headers={"Authorization": f"Bearer {token}"})
    if response.status_code >= 400:
        raise HTTPException(401, "Google Play 购买凭证无效")
    data = response.json()
    items = data.get("lineItems") or []
    item = next((x for x in items if x.get("productId") == product_id), None)
    if not item or data.get("subscriptionState") not in {
        "SUBSCRIPTION_STATE_ACTIVE",
        "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
        "SUBSCRIPTION_STATE_CANCELED",
    }:
        raise HTTPException(402, "Google Play 订阅未处于有效状态")
    expiry = str(item.get("expiryTime") or "")
    expires_ms = 0
    if expiry:
        try:
            expires_ms = int(datetime.fromisoformat(expiry.replace("Z", "+00:00")).timestamp() * 1000)
        except (TypeError, ValueError, OverflowError):
            expires_ms = 0
    return {
        "plan": PLAY_PRODUCTS[product_id],
        "status": "active" if expires_ms > int(time.time() * 1000) else "expired",
        "expires_at": expires_ms,
        "product_id": product_id,
        "purchase_token": purchase_token,
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
    if effective_plan(user) == "admin":
        raise HTTPException(400, "管理员账号无需订阅")
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


@router.post("/api/billing/google-play/verify")
def verify_google_play(request: Request, payload: dict = Body(default={} )):
    user = _require_user(request)
    product_id = str(payload.get("product_id") or "").strip()
    purchase_token = str(payload.get("purchase_token") or "").strip()
    result = _verify_play_purchase(product_id, purchase_token)
    updated = update_billing_user(
        user["id"],
        plan=result["plan"],
        plan_status=result["status"],
        plan_expires_at=result["expires_at"],
        google_play_product_id=result["product_id"],
        google_play_purchase_token=result["purchase_token"],
    )
    return {"ok": True, "plan": result["plan"], "status": result["status"], "expires_at": result["expires_at"], "user": updated}


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
