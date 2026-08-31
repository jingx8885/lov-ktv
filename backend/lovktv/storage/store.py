from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import uuid
from typing import Any

from lovktv.core.config import DB_PATH, MEDIA_DIR, QR_TTL_MS, SESSION_DAYS
from lovktv.core.db import connect as db_connect
from lovktv.core.db import execute, init_schema
from lovktv.core.schema import SONG_FIELDS
from lovktv.identity.passwords import (
    hash_password,
    normalize_username,
    username_key,
    verify_password,
)
from lovktv.storage.media import (
    media_flags as _media_flags,
)
from lovktv.storage.media import (
    media_rev as _media_rev,
)
from lovktv.storage.media import (
    with_media_flags as _with_media_flags,
)

READY = "ready"
BUSY = {"fetching", "separating", "aligning", "annotating", "composing"}
LYRIC_MODES = ("ja", "zh", "roma", "all")
DISPLAY_MODES = ("lyrics", "mv")


def normalize_lyric_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LYRIC_MODES else "all"


def normalize_display_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in DISPLAY_MODES else "mv"


_LOCK = threading.Lock()


def connect():
    return db_connect(DB_PATH)


def init_db() -> None:
    with connect() as conn:
        init_schema(conn)


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def create_song(
    title: str, artist: str = "", language: str = "zh", netease_id: str = ""
) -> dict[str, Any]:
    song_id = new_id()
    with _LOCK, connect() as conn:
        execute(
            conn,
            "INSERT INTO songs (id, title, artist, language, status, netease_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (song_id, title, artist, language, "queued", netease_id, now_ms()),
        )
    (MEDIA_DIR / song_id).mkdir(parents=True, exist_ok=True)
    return get_song(song_id)


def update_song(song_id: str, **fields: Any) -> None:
    allowed = {key: value for key, value in fields.items() if key in SONG_FIELDS}
    if not allowed:
        return
    assignments = ", ".join(f"{key}=?" for key in allowed)
    with _LOCK, connect() as conn:
        execute(
            conn,
            f"UPDATE songs SET {assignments} WHERE id=?",
            (*allowed.values(), song_id),
        )


def get_song(song_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = execute(conn, "SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    return _row(row)


def media_rev(song_id: str) -> str:
    return _media_rev(song_id, MEDIA_DIR)


def media_flags(song_id: str) -> dict[str, Any]:
    return _media_flags(song_id, MEDIA_DIR)


def with_media_flags(song: dict[str, Any] | None) -> dict[str, Any] | None:
    return _with_media_flags(song, MEDIA_DIR)


def list_songs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = execute(
            conn, "SELECT * FROM songs ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def _count_value(row: Any) -> int:
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def _clamp_room_indexes(conn: Any) -> None:
    rooms = execute(conn, "SELECT code, now_index FROM rooms").fetchall()
    for room in rooms:
        count = _count_value(
            execute(
                conn, "SELECT COUNT(*) FROM queue WHERE room=?", (room["code"],)
            ).fetchone()
        )
        if count <= 0:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (room["code"],))
        elif int(room["now_index"]) < 0:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (room["code"],))
        elif int(room["now_index"]) >= count:
            execute(
                conn,
                "UPDATE rooms SET now_index=? WHERE code=?",
                (count - 1, room["code"]),
            )


def delete_song(song_id: str) -> bool:
    song = get_song(song_id)
    if not song:
        return False
    with _LOCK, connect() as conn:
        execute(conn, "DELETE FROM queue WHERE song_id=?", (song_id,))
        execute(conn, "DELETE FROM songs WHERE id=?", (song_id,))
        _clamp_room_indexes(conn)
    folder = MEDIA_DIR / song_id
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    return True


def retry_query(song: dict[str, Any]) -> str:
    title = str(song.get("title") or "").strip()
    artist = str(song.get("artist") or "").strip()
    if " · " in title:
        title = title.split(" · ", 1)[0].strip()
    return " ".join(part for part in (title, artist) if part)


def host_keys(machine: str = "", ua: str = "", ip: str = "") -> list[str]:
    keys: list[str] = []
    mid = "".join(ch for ch in str(machine or "") if ch.isalnum() or ch in "-_")[:64]
    if len(mid) >= 8:
        keys.append("m:" + mid)
    ua_n = " ".join(str(ua or "").split())[:240]
    ip_n = str(ip or "").split("%")[0].strip()
    if ua_n or ip_n:
        digest = hashlib.sha256(f"{ua_n}|{ip_n}".encode()).hexdigest()[:32]
        keys.append("u:" + digest)
    return keys


def write_json(path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _user_row(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    user_id = str(data["id"])
    username = str(data.get("username") or "")
    wechat = bool(data.get("wechat_openid"))
    return {
        "id": user_id,
        "sid": user_id[:6].upper(),
        "nickname": data.get("nickname") or username or f"ID {user_id[:6].upper()}",
        "avatar": data.get("avatar") or "",
        "wechat": wechat,
        "username": username,
        "account": bool(username or wechat),
        "created_at": int(data.get("created_at") or 0),
    }


def get_user(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = execute(conn, "SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_row(row)


def list_users(query: str = "", limit: int = 80) -> list[dict[str, Any]]:
    needle = str(query or "").strip()
    limit = max(1, min(int(limit or 80), 200))
    with connect() as conn:
        rows = execute(
            conn, "SELECT * FROM users ORDER BY created_at DESC, id DESC"
        ).fetchall()
    out: list[dict[str, Any]] = []
    key = needle.casefold()
    for row in rows:
        user = _user_row(row)
        if not user:
            continue
        if key:
            blob = " ".join(
                [
                    user.get("id") or "",
                    user.get("sid") or "",
                    user.get("username") or "",
                    user.get("nickname") or "",
                ]
            ).casefold()
            if key not in blob and f"u:{user['id']}".casefold() != key:
                continue
        out.append(user)
        if len(out) >= limit:
            break
    return out


def upsert_wechat_user(
    openid: str, unionid: str = "", nickname: str = "", avatar: str = ""
) -> dict[str, Any]:
    openid = (openid or "").strip()
    if not openid:
        raise ValueError("微信未返回账号")
    now = now_ms()
    with _LOCK, connect() as conn:
        row = execute(
            conn, "SELECT * FROM users WHERE wechat_openid=?", (openid,)
        ).fetchone()
        if row:
            user_id = row["id"]
            execute(
                conn,
                "UPDATE users SET wechat_unionid=?, nickname=?, avatar=? WHERE id=?",
                (
                    unionid or row["wechat_unionid"],
                    nickname or row["nickname"],
                    avatar or row["avatar"],
                    user_id,
                ),
            )
        else:
            user_id = new_id()
            execute(
                conn,
                "INSERT INTO users (id, wechat_openid, wechat_unionid, nickname, avatar, created_at) VALUES (?,?,?,?,?,?)",
                (
                    user_id,
                    openid,
                    unionid,
                    nickname or f"ID {user_id[:6].upper()}",
                    avatar,
                    now,
                ),
            )
    user = get_user(user_id)
    if not user:
        raise RuntimeError("创建用户失败")
    return user


def upsert_device_user(device_id: str, nickname: str = "") -> dict[str, Any]:
    device_id = (device_id or "").strip()[:64]
    if len(device_id) < 8:
        raise ValueError("无效的设备")
    now = now_ms()
    with _LOCK, connect() as conn:
        row = execute(
            conn, "SELECT * FROM users WHERE device_id=?", (device_id,)
        ).fetchone()
        if row:
            user_id = row["id"]
            if nickname and nickname != row["nickname"]:
                execute(
                    conn, "UPDATE users SET nickname=? WHERE id=?", (nickname, user_id)
                )
        else:
            user_id = new_id()
            execute(
                conn,
                "INSERT INTO users (id, device_id, nickname, created_at) VALUES (?,?,?,?)",
                (user_id, device_id, nickname or f"ID {user_id[:6].upper()}", now),
            )
    user = get_user(user_id)
    if not user:
        raise RuntimeError("创建用户失败")
    return user


def create_session(user_id: str, days: int | None = None) -> str:
    days = SESSION_DAYS if days is None else days
    token = uuid.uuid4().hex + uuid.uuid4().hex
    now = now_ms()
    with _LOCK, connect() as conn:
        execute(
            conn,
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, user_id, now, now + days * 86400_000),
        )
    return token


def user_from_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    now = now_ms()
    with connect() as conn:
        row = execute(
            conn,
            "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token=? AND sessions.expires_at>?",
            (token, now),
        ).fetchone()
    return _user_row(row)


def delete_session(token: str) -> None:
    if not token:
        return
    with _LOCK, connect() as conn:
        execute(conn, "DELETE FROM sessions WHERE token=?", (token,))


def get_user_by_username(name: str) -> dict[str, Any] | None:
    try:
        key = username_key(name)
    except ValueError:
        return None
    with connect() as conn:
        row = execute(
            conn, "SELECT * FROM users WHERE username_key=?", (key,)
        ).fetchone()
    return dict(row) if row else None


def register_password_user(
    name: str, password: str, attach_user_id: str = ""
) -> dict[str, Any]:
    username = normalize_username(name)
    key = username_key(username)
    hashed = hash_password(password)
    now = now_ms()
    with _LOCK, connect() as conn:
        taken = execute(
            conn, "SELECT id FROM users WHERE username_key=?", (key,)
        ).fetchone()
        if taken:
            raise ValueError("这个用户名已经被用了")
        attached = None
        if attach_user_id:
            row = execute(
                conn, "SELECT * FROM users WHERE id=?", (attach_user_id,)
            ).fetchone()
            attached = dict(row) if row else None
        if attached and not str(attached.get("username") or ""):
            execute(
                conn,
                "UPDATE users SET username=?, username_key=?, password_hash=?, nickname=? WHERE id=?",
                (
                    username,
                    key,
                    hashed,
                    username,
                    attach_user_id,
                ),
            )
            user_id = attach_user_id
        else:
            user_id = new_id()
            execute(
                conn,
                "INSERT INTO users (id, username, username_key, password_hash, nickname, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, username, key, hashed, username, now),
            )
    user = get_user(user_id)
    if not user:
        raise RuntimeError("创建用户失败")
    return user


def update_password_user(
    user_id: str, nickname: str = "", password: str = ""
) -> dict[str, Any]:
    user = get_user(user_id)
    if not user:
        raise ValueError("管理找不到这个账号")
    nick = str(nickname or "").strip()[:32]
    hashed = hash_password(password) if str(password or "") else ""
    with _LOCK, connect() as conn:
        if nick:
            execute(conn, "UPDATE users SET nickname=? WHERE id=?", (nick, user_id))
        if hashed:
            execute(
                conn, "UPDATE users SET password_hash=? WHERE id=?", (hashed, user_id)
            )
    updated = get_user(user_id)
    if not updated:
        raise RuntimeError("创建用户失败")
    return updated


def login_password_user(name: str, password: str) -> dict[str, Any]:
    row = get_user_by_username(name)
    if not row or not verify_password(password, str(row.get("password_hash") or "")):
        raise ValueError("用户名或密码不对")
    user = get_user(str(row["id"]))
    if not user:
        raise ValueError("用户名或密码不对")
    return user


def guest_song_used(key: str, day: str) -> int:
    if not key or not day:
        return 0
    with connect() as conn:
        row = execute(
            conn,
            "SELECT used FROM guest_song_counts WHERE guest_key=? AND day=?",
            (key, day),
        ).fetchone()
    if not row:
        return 0
    data = dict(row)
    return int(data.get("used") or 0)


def increment_guest_song(key: str, day: str) -> int:
    if not key or not day:
        return 0
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT used FROM guest_song_counts WHERE guest_key=? AND day=?",
            (key, day),
        ).fetchone()
        used = int(dict(row).get("used") or 0) if row else 0
        nxt = used + 1
        if row:
            execute(
                conn,
                "UPDATE guest_song_counts SET used=? WHERE guest_key=? AND day=?",
                (nxt, key, day),
            )
        else:
            execute(
                conn,
                "INSERT INTO guest_song_counts (guest_key, day, used) VALUES (?,?,?)",
                (key, day, nxt),
            )
    return nxt


def create_login_ticket(ttl_ms: int | None = None) -> dict[str, Any]:
    ttl_ms = QR_TTL_MS if ttl_ms is None else ttl_ms
    ticket = uuid.uuid4().hex[:10]
    now = now_ms()
    with _LOCK, connect() as conn:
        execute(
            conn,
            "INSERT INTO login_tickets (id, status, created_at, expires_at) VALUES (?,?,?,?)",
            (ticket, "pending", now, now + ttl_ms),
        )
    return {"ticket": ticket, "expires_at": now + ttl_ms}


def get_login_ticket(ticket: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = execute(
            conn, "SELECT * FROM login_tickets WHERE id=?", (ticket,)
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    if data["status"] == "pending" and int(data["expires_at"]) <= now_ms():
        with _LOCK, connect() as conn:
            execute(
                conn,
                "UPDATE login_tickets SET status='expired' WHERE id=? AND status='pending'",
                (ticket,),
            )
        data["status"] = "expired"
    return data


def confirm_login_ticket(ticket: str, user_id: str) -> dict[str, Any]:
    row = get_login_ticket(ticket)
    if not row or row["status"] != "pending":
        raise ValueError("二维码已过期，请刷新")
    with _LOCK, connect() as conn:
        execute(
            conn,
            "UPDATE login_tickets SET status='confirmed', user_id=? WHERE id=? AND status='pending'",
            (user_id, ticket),
        )
    return get_login_ticket(ticket) or row


def consume_confirmed_ticket(ticket: str) -> dict[str, Any] | None:
    row = get_login_ticket(ticket)
    if not row or row["status"] != "confirmed" or not row.get("user_id"):
        return None
    user = get_user(str(row["user_id"]))
    if not user:
        return None
    with _LOCK, connect() as conn:
        cur = execute(
            conn,
            "UPDATE login_tickets SET status='used' WHERE id=? AND status='confirmed'",
            (ticket,),
        )
        if cur.rowcount != 1:
            return None
    return user


def upsert_songs(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    keys = (
        "id",
        "title",
        "artist",
        "language",
        "status",
        "error",
        "audio_source",
        "netease_id",
        "created_at",
    )
    init_db()
    with _LOCK, connect() as conn:
        for row in rows:
            values = [row.get(key, "") for key in keys]
            execute(
                conn,
                """
                INSERT INTO songs (id, title, artist, language, status, error, audio_source, netease_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  title=excluded.title,
                  artist=excluded.artist,
                  language=excluded.language,
                  status=excluded.status,
                  error=excluded.error,
                  audio_source=excluded.audio_source,
                  netease_id=excluded.netease_id
                """,
                values,
            )
    return len(rows)
