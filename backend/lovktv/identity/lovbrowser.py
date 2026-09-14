"""Small, server-side OIDC client for the LovBrowser identity provider.

The KTV process never reads LovBrowser's database.  It exchanges a one-time
authorization code over TLS and links the returned stable ``sub`` locally.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.parse import urlparse, urlencode

import httpx

from lovktv.core import config

_EPHEMERAL_STATE_SECRET = secrets.token_urlsafe(32)


def enabled() -> bool:
    return bool(config.LOVBROWSER_OIDC_CLIENT_ID and config.LOVBROWSER_OIDC_CLIENT_SECRET)


def _discovery_url() -> str:
    return _trusted_endpoint(config.LOVBROWSER_OIDC_DISCOVERY_URL or f"{config.LOVBROWSER_OIDC_ISSUER}/.well-known/openid-configuration")


def _trusted_endpoint(value: Any) -> str:
    endpoint = str(value or "").strip()
    issuer = urlparse(config.LOVBROWSER_OIDC_ISSUER)
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or parsed.hostname != issuer.hostname:
        raise ValueError("LovBrowser OIDC 端点不是受信任的 HTTPS 地址")
    return endpoint


def _state_secret() -> bytes:
    # Production must provide a stable secret; the process-random fallback is
    # deliberately useful only for local tests and makes restart invalidate state.
    return (config.LOVBROWSER_OIDC_STATE_SECRET or _EPHEMERAL_STATE_SECRET).encode()


def make_state(next_path: str = "") -> tuple[str, str]:
    nonce = secrets.token_urlsafe(24)
    payload = json.dumps({"n": nonce, "next": next_path if next_path.startswith("/") else "/"}, separators=(",", ":"), ensure_ascii=True).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    sig = hmac.new(_state_secret(), encoded.encode(), hashlib.sha256).digest()
    state = encoded + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    verifier = secrets.token_urlsafe(48)
    return state, verifier


def verify_state(state: str, expected: str) -> str:
    if not state or not expected or not hmac.compare_digest(state, expected):
        raise ValueError("LovBrowser 登录状态无效或已过期")
    encoded, sep, signature = state.partition(".")
    if not sep:
        raise ValueError("LovBrowser 登录状态无效")
    expected_sig = base64.urlsafe_b64encode(hmac.new(_state_secret(), encoded.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("LovBrowser 登录状态签名无效")
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
    except Exception as exc:
        raise ValueError("LovBrowser 登录状态损坏") from exc
    return str(payload.get("next") or "/") if str(payload.get("next") or "/").startswith("/") else "/"


def code_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _http(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ValueError("LovBrowser 登录服务暂时不可用") from exc
    if not isinstance(data, dict):
        raise ValueError("LovBrowser 返回格式无效")
    return data


def authorization_url(redirect_uri: str, state: str, verifier: str) -> str:
    if not enabled():
        raise ValueError("尚未配置 LovBrowser 登录")
    metadata = _http("GET", _discovery_url())
    endpoint = _trusted_endpoint(metadata.get("authorization_endpoint"))
    if not endpoint:
        raise ValueError("LovBrowser 未提供授权端点")
    return endpoint + "?" + urlencode({
        "response_type": "code", "client_id": config.LOVBROWSER_OIDC_CLIENT_ID,
        "redirect_uri": redirect_uri, "scope": config.LOVBROWSER_OIDC_SCOPES,
        "state": state, "code_challenge": code_challenge(verifier), "code_challenge_method": "S256",
    })


def exchange_code(code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
    if not code:
        raise ValueError("LovBrowser 未返回授权码")
    metadata = _http("GET", _discovery_url())
    token_endpoint = _trusted_endpoint(metadata.get("token_endpoint"))
    userinfo_endpoint = _trusted_endpoint(metadata.get("userinfo_endpoint"))
    if not token_endpoint or not userinfo_endpoint:
        raise ValueError("LovBrowser OIDC 配置不完整")
    token = _http("POST", token_endpoint, data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": redirect_uri, "client_id": config.LOVBROWSER_OIDC_CLIENT_ID,
        "code_verifier": verifier,
    }, auth=(config.LOVBROWSER_OIDC_CLIENT_ID, config.LOVBROWSER_OIDC_CLIENT_SECRET))
    access_token = str(token.get("access_token") or "")
    if not access_token:
        raise ValueError("LovBrowser 未返回 access token")
    user = _http("GET", userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
    if not str(user.get("sub") or "").strip():
        raise ValueError("LovBrowser 用户资料缺少 subject")
    return user
