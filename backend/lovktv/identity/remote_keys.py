"""Member remote credentials: one revocable, hashed key per account."""

import hashlib
import secrets
import time
import uuid

from fastapi import HTTPException
from starlette.requests import Request

from lovktv.storage import store

INVALID_KEY = "API key 无效或已失效"


def is_member(user):
    return bool(
        user
        and user.get("plan") in {"starter", "pro"}
        and user.get("plan_status") in {"active", "trialing"}
        and (
            not user.get("plan_expires_at")
            or int(user["plan_expires_at"]) > int(time.time() * 1000)
        )
    )


def key_info(user_id):
    with store.connect() as conn:
        row = store.execute(
            conn,
            "SELECT id,prefix,created_at FROM remote_api_keys WHERE user_id=?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def issue_key(user_id):
    token = "lkr_" + secrets.token_urlsafe(32)
    with store.connect() as conn:
        store.execute(
            conn,
            "INSERT INTO remote_api_keys(id,user_id,key_hash,prefix,created_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "id=excluded.id,key_hash=excluded.key_hash,prefix=excluded.prefix,created_at=excluded.created_at",
            (
                uuid.uuid4().hex,
                user_id,
                hashlib.sha256(token.encode()).hexdigest(),
                token[:10],
                int(time.time() * 1000),
            ),
        )
    return token


def require_key(request: Request):
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not token.startswith("lkr_") or len(token) > 128:
        raise HTTPException(401, INVALID_KEY)
    with store.connect() as conn:
        row = store.execute(
            conn,
            "SELECT user_id FROM remote_api_keys WHERE key_hash=?",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchone()
    user = store.get_user(row["user_id"]) if row else None
    if not is_member(user):
        raise HTTPException(401, INVALID_KEY)
    return user
