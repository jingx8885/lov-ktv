from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
import uuid
from typing import Any

from lovktv.config import DB_PATH, MEDIA_DIR, QR_TTL_MS, SESSION_DAYS

READY = "ready"
BUSY = {"fetching", "separating", "aligning", "annotating", "composing"}

_LOCK = threading.Lock()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS songs (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              artist TEXT NOT NULL DEFAULT '',
              language TEXT NOT NULL DEFAULT 'zh',
              status TEXT NOT NULL DEFAULT 'queued',
              error TEXT NOT NULL DEFAULT '',
              audio_source TEXT NOT NULL DEFAULT '',
              netease_id TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rooms (
              code TEXT PRIMARY KEY,
              created_at INTEGER NOT NULL,
              vocal_mix REAL NOT NULL DEFAULT 1,
              volume INTEGER NOT NULL DEFAULT 80,
              now_index INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS queue (
              id TEXT PRIMARY KEY,
              room TEXT NOT NULL,
              song_id TEXT NOT NULL,
              position INTEGER NOT NULL,
              created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              wechat_openid TEXT NOT NULL DEFAULT '',
              wechat_unionid TEXT NOT NULL DEFAULT '',
              device_id TEXT NOT NULL DEFAULT '',
              nickname TEXT NOT NULL DEFAULT '',
              avatar TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_tickets (
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              user_id TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL
            );
            """
        )


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def create_song(title: str, artist: str = "", language: str = "zh", netease_id: str = "") -> dict[str, Any]:
    song_id = new_id()
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO songs (id, title, artist, language, status, netease_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (song_id, title, artist, language, "queued", netease_id, now_ms()),
        )
    (MEDIA_DIR / song_id).mkdir(parents=True, exist_ok=True)
    return get_song(song_id)


def update_song(song_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key}=?" for key in fields)
    with _LOCK, connect() as conn:
        conn.execute(f"UPDATE songs SET {assignments} WHERE id=?", (*fields.values(), song_id))


def get_song(song_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    return dict(row) if row else None


def list_songs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM songs ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def _clamp_room_indexes(conn: sqlite3.Connection) -> None:
    rooms = conn.execute("SELECT code, now_index FROM rooms").fetchall()
    for room in rooms:
        count = conn.execute("SELECT COUNT(*) FROM queue WHERE room=?", (room["code"],)).fetchone()[0]
        if count <= 0:
            conn.execute("UPDATE rooms SET now_index=0 WHERE code=?", (room["code"],))
        elif int(room["now_index"]) >= count:
            conn.execute("UPDATE rooms SET now_index=? WHERE code=?", (count - 1, room["code"]))


def delete_song(song_id: str) -> bool:
    song = get_song(song_id)
    if not song:
        return False
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM queue WHERE song_id=?", (song_id,))
        conn.execute("DELETE FROM songs WHERE id=?", (song_id,))
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


def ensure_room(code: str | None = None) -> dict[str, Any]:
    if not code:
        code = uuid.uuid4().hex[:6].upper()
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT * FROM rooms WHERE code=?", (code,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO rooms (code, created_at) VALUES (?,?)",
                (code, now_ms()),
            )
            row = conn.execute("SELECT * FROM rooms WHERE code=?", (code,)).fetchone()
    return dict(row)


def room_snapshot(code: str) -> dict[str, Any]:
    room = ensure_room(code)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT queue.id, queue.song_id, queue.position, songs.title, songs.artist, songs.status, songs.language
            FROM queue JOIN songs ON songs.id = queue.song_id
            WHERE queue.room=? ORDER BY queue.position ASC, queue.created_at ASC
            """,
            (code,),
        ).fetchall()
    queue = [dict(row) for row in rows]
    now = queue[room["now_index"]] if queue and 0 <= room["now_index"] < len(queue) else None
    return {**room, "queue": queue, "now_playing": now}


def enqueue(code: str, song_id: str) -> dict[str, Any]:
    code = code.upper()
    ensure_room(code)
    song = get_song(song_id)
    if not song or song.get("status") != READY:
        raise ValueError("这首还没就绪，不能点")
    snap = room_snapshot(code)
    if any(item["song_id"] == song_id for item in snap["queue"]):
        return snap
    had_playing = snap.get("now_playing") is not None
    with _LOCK, connect() as conn:
        pos = conn.execute("SELECT COALESCE(MAX(position),0)+1 FROM queue WHERE room=?", (code,)).fetchone()[0]
        conn.execute(
            "INSERT INTO queue (id, room, song_id, position, created_at) VALUES (?,?,?,?,?)",
            (new_id(), code, song_id, pos, now_ms()),
        )
        if not had_playing:
            conn.execute("UPDATE rooms SET now_index=-1 WHERE code=?", (code,))
    return room_snapshot(code)


def bump(code: str, item_id: str) -> dict[str, Any]:
    snap = room_snapshot(code)
    items = snap["queue"]
    idx = next((i for i, item in enumerate(items) if item["id"] == item_id), None)
    if idx is None or idx <= snap["now_index"] + 1:
        return snap
    target_pos = items[snap["now_index"] + 1]["position"] if len(items) > snap["now_index"] + 1 else items[idx]["position"]
    with _LOCK, connect() as conn:
        conn.execute("UPDATE queue SET position=? WHERE id=?", (target_pos - 1, item_id))
    return room_snapshot(code)


def skip(code: str) -> dict[str, Any]:
    """Remove the current song from the queue and play the next one."""
    code = code.upper()
    snap = room_snapshot(code)
    queue = snap["queue"]
    if not queue or snap.get("now_playing") is None:
        return snap
    cur = max(0, min(snap["now_index"], len(queue) - 1))
    item_id = queue[cur]["id"]
    remaining = len(queue) - 1
    nxt = 0 if remaining <= 0 or cur >= remaining else cur
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM queue WHERE id=?", (item_id,))
        conn.execute("UPDATE rooms SET now_index=? WHERE code=?", (nxt, code))
    return room_snapshot(code)


def play_now(code: str, item_id: str = "", song_id: str = "") -> dict[str, Any]:
    """Jump to a queue item. A bare song_id only starts the room if nothing is on."""
    code = code.upper()
    if song_id and not item_id:
        snap = room_snapshot(code)
        if snap.get("now_playing"):
            enqueue(code, song_id)
            return room_snapshot(code)
        existing = next((item for item in snap["queue"] if item["song_id"] == song_id), None)
        if existing is None:
            song = get_song(song_id)
            if not song or song.get("status") != READY:
                raise ValueError("这首还没就绪，不能点")
            enqueue(code, song_id)
            snap = room_snapshot(code)
            existing = next((item for item in snap["queue"] if item["song_id"] == song_id), None)
        item_id = existing["id"] if existing else ""
    snap = room_snapshot(code)
    idx = next((i for i, item in enumerate(snap["queue"]) if item["id"] == item_id), None)
    if idx is None:
        return snap
    if snap["queue"][idx].get("status") != READY:
        raise ValueError("这首还没就绪，不能点")
    with _LOCK, connect() as conn:
        conn.execute("UPDATE rooms SET now_index=? WHERE code=?", (idx, code))
    return room_snapshot(code)


def set_mix(code: str, vocal_mix: float | None = None, volume: int | None = None) -> dict[str, Any]:
    fields = {}
    if vocal_mix is not None:
        fields["vocal_mix"] = max(0.0, min(1.0, vocal_mix))
    if volume is not None:
        fields["volume"] = max(0, min(100, volume))
    if fields:
        assignments = ", ".join(f"{key}=?" for key in fields)
        with _LOCK, connect() as conn:
            conn.execute(f"UPDATE rooms SET {assignments} WHERE code=?", (*fields.values(), code))
    return room_snapshot(code)


def write_json(path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _user_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    return {
        "id": data["id"],
        "nickname": data.get("nickname") or "KTV 用户",
        "avatar": data.get("avatar") or "",
        "wechat": bool(data.get("wechat_openid")),
    }


def get_user(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_row(row)


def upsert_wechat_user(openid: str, unionid: str = "", nickname: str = "", avatar: str = "") -> dict[str, Any]:
    openid = (openid or "").strip()
    if not openid:
        raise ValueError("微信未返回账号")
    now = now_ms()
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE wechat_openid=?", (openid,)).fetchone()
        if row:
            user_id = row["id"]
            conn.execute(
                "UPDATE users SET wechat_unionid=?, nickname=?, avatar=? WHERE id=?",
                (unionid or row["wechat_unionid"], nickname or row["nickname"], avatar or row["avatar"], user_id),
            )
        else:
            user_id = new_id()
            conn.execute(
                "INSERT INTO users (id, wechat_openid, wechat_unionid, nickname, avatar, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, openid, unionid, nickname or "微信用户", avatar, now),
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
        row = conn.execute("SELECT * FROM users WHERE device_id=?", (device_id,)).fetchone()
        if row:
            user_id = row["id"]
            if nickname and nickname != row["nickname"]:
                conn.execute("UPDATE users SET nickname=? WHERE id=?", (nickname, user_id))
        else:
            user_id = new_id()
            conn.execute(
                "INSERT INTO users (id, device_id, nickname, created_at) VALUES (?,?,?,?)",
                (user_id, device_id, nickname or "手机用户", now),
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
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, user_id, now, now + days * 86400_000),
        )
    return token


def user_from_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    now = now_ms()
    with connect() as conn:
        row = conn.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token=? AND sessions.expires_at>?",
            (token, now),
        ).fetchone()
    return _user_row(row)


def delete_session(token: str) -> None:
    if not token:
        return
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))


def create_login_ticket(ttl_ms: int | None = None) -> dict[str, Any]:
    ttl_ms = QR_TTL_MS if ttl_ms is None else ttl_ms
    ticket = uuid.uuid4().hex[:10]
    now = now_ms()
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO login_tickets (id, status, created_at, expires_at) VALUES (?,?,?,?)",
            (ticket, "pending", now, now + ttl_ms),
        )
    return {"ticket": ticket, "expires_at": now + ttl_ms}


def get_login_ticket(ticket: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM login_tickets WHERE id=?", (ticket,)).fetchone()
    if not row:
        return None
    data = dict(row)
    if data["status"] == "pending" and int(data["expires_at"]) <= now_ms():
        with _LOCK, connect() as conn:
            conn.execute("UPDATE login_tickets SET status='expired' WHERE id=? AND status='pending'", (ticket,))
        data["status"] = "expired"
    return data


def confirm_login_ticket(ticket: str, user_id: str) -> dict[str, Any]:
    row = get_login_ticket(ticket)
    if not row or row["status"] != "pending":
        raise ValueError("二维码已过期，请刷新")
    with _LOCK, connect() as conn:
        conn.execute(
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
        cur = conn.execute(
            "UPDATE login_tickets SET status='used' WHERE id=? AND status='confirmed'",
            (ticket,),
        )
        if cur.rowcount != 1:
            return None
    return user
