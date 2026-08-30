"""Username + password helpers. Fast room-PIN style accounts."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

_USERNAME = re.compile(r"^[\w.\-]{1,32}$", re.UNICODE)
_PBKDF2_ROUNDS = 120_000


def normalize_username(raw: str) -> str:
    name = str(raw or "").strip()
    if not _USERNAME.fullmatch(name):
        raise ValueError("用户名只能用字、数字和 ._-，1 到 32 个")
    return name


def username_key(name: str) -> str:
    return normalize_username(name).casefold()


def normalize_password(raw: str) -> str:
    password = str(raw or "")
    if len(password) < 4 or len(password) > 72:
        raise ValueError("密码至少 4 位")
    return password


def hash_password(password: str) -> str:
    password = normalize_password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS
    )
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = str(stored or "").split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        got = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            bytes.fromhex(salt),
            int(rounds),
        )
        return hmac.compare_digest(got.hex(), digest)
    except Exception:
        return False
