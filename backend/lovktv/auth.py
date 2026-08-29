"""WeChat OAuth + QR login helpers."""

from __future__ import annotations

from urllib.parse import quote, urlencode

import httpx

from lovktv.config import (
    PUBLIC_URL,
    WECHAT_APP_ID,
    WECHAT_APP_SECRET,
    WECHAT_MP_APP_ID,
    WECHAT_MP_APP_SECRET,
)

SESSION_COOKIE = "lovktv_session"


def wechat_ready(kind: str = "web") -> bool:
    if kind == "mp":
        return bool(WECHAT_MP_APP_ID and WECHAT_MP_APP_SECRET)
    return bool(WECHAT_APP_ID and WECHAT_APP_SECRET)


def auth_status() -> dict:
    return {
        "wechat": wechat_ready("web"),
        "wechat_quick": wechat_ready("mp"),
        "qr": True,
    }


def public_base(request_base: str = "") -> str:
    return PUBLIC_URL or request_base.rstrip("/")


def wechat_authorize_url(
    redirect_uri: str, state: str, quick: bool = False, silent: bool = False
) -> str:
    if (quick or silent) and wechat_ready("mp"):
        app_id = WECHAT_MP_APP_ID
        scope = "snsapi_base" if silent else "snsapi_userinfo"
        host = "https://open.weixin.qq.com/connect/oauth2/authorize"
    elif wechat_ready("web"):
        app_id = WECHAT_APP_ID
        scope = "snsapi_login"
        host = "https://open.weixin.qq.com/connect/qrconnect"
    else:
        raise ValueError("还没配置微信开放平台 AppID")
    query = urlencode(
        {
            "appid": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
    )
    return f"{host}?{query}#wechat_redirect"


def exchange_wechat_code(code: str, quick: bool = False, silent: bool = False) -> dict:
    use_mp = (quick or silent) and wechat_ready("mp")
    app_id = WECHAT_MP_APP_ID if use_mp else WECHAT_APP_ID
    secret = WECHAT_MP_APP_SECRET if use_mp else WECHAT_APP_SECRET
    if not app_id or not secret:
        raise ValueError("还没配置微信开放平台 AppID")
    token_url = "https://api.weixin.qq.com/sns/oauth2/access_token?" + urlencode(
        {
            "appid": app_id,
            "secret": secret,
            "code": code,
            "grant_type": "authorization_code",
        }
    )
    with httpx.Client(timeout=12) as client:
        token = client.get(token_url).json()
        if token.get("errcode") or not token.get("access_token"):
            raise ValueError(str(token.get("errmsg") or "微信授权失败"))
        if silent:
            return {
                "openid": str(token.get("openid") or ""),
                "unionid": str(token.get("unionid") or ""),
                "nickname": "",
                "avatar": "",
            }
        info = client.get(
            "https://api.weixin.qq.com/sns/userinfo?"
            + urlencode(
                {
                    "access_token": token["access_token"],
                    "openid": token["openid"],
                    "lang": "zh_CN",
                }
            )
        ).json()
    if info.get("errcode"):
        raise ValueError(str(info.get("errmsg") or "读取微信资料失败"))
    return {
        "openid": str(token.get("openid") or ""),
        "unionid": str(token.get("unionid") or info.get("unionid") or ""),
        "nickname": str(info.get("nickname") or "微信用户"),
        "avatar": str(info.get("headimgurl") or ""),
    }


def in_wechat(user_agent: str) -> bool:
    return "MicroMessenger" in (user_agent or "")


def scan_login_url(
    base: str, ticket: str = "", room: str = "", next_path: str = ""
) -> str:
    query = []
    if ticket:
        query.append(f"ticket={quote(ticket)}")
    if room:
        query.append(f"room={quote(room)}")
    if next_path:
        query.append(f"next={quote(next_path)}")
    suffix = ("?" + "&".join(query)) if query else ""
    return f"{base.rstrip('/')}/api/auth/scan{suffix}"


def done_login_path(ticket: str = "", room: str = "", next_path: str = "") -> str:
    if next_path.startswith("/"):
        return next_path
    return login_page_url("", ticket=ticket, room=room, ok=True)


def encode_state(kind: str, ticket: str = "", next_path: str = "") -> str:
    return "|".join([kind or "web", ticket or "", next_path or ""])[:128]


def decode_state(state: str) -> tuple[str, str, str]:
    parts = (state or "web").split("|", 2)
    kind = parts[0] or "web"
    ticket = parts[1] if len(parts) > 1 else ""
    next_path = parts[2] if len(parts) > 2 else ""
    return kind, ticket, next_path


def login_page_url(
    base: str,
    ticket: str = "",
    room: str = "",
    next_path: str = "",
    error: str = "",
    ok: bool = False,
) -> str:
    query = []
    if ticket:
        query.append(f"login={quote(ticket)}")
    if room:
        query.append(f"room={quote(room)}")
    if next_path:
        query.append(f"next={quote(next_path)}")
    if error:
        query.append(f"error={quote(error)}")
    if ok:
        query.append("ok=1")
    suffix = ("?" + "&".join(query)) if query else ""
    return f"{base}/login.html{suffix}"
