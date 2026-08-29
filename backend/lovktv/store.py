from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import uuid
from typing import Any

from lovktv.config import DB_PATH, MEDIA_DIR, QR_TTL_MS, SESSION_DAYS
from lovktv.db import connect as db_connect
from lovktv.db import execute, init_schema
from lovktv.schema import ROOM_FIELDS, SONG_FIELDS

READY = "ready"
BUSY = {"fetching", "separating", "aligning", "annotating", "composing"}
LYRIC_MODES = ("ja", "zh", "roma", "all")


def normalize_lyric_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LYRIC_MODES else "all"

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


def create_song(title: str, artist: str = "", language: str = "zh", netease_id: str = "") -> dict[str, Any]:
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
        execute(conn, f"UPDATE songs SET {assignments} WHERE id=?", (*allowed.values(), song_id))


def get_song(song_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = execute(conn, "SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    return _row(row)


_MEDIA_REV_NAMES = (
    "cover.jpg",
    "guide.m4a",
    "karaoke.m4a",
    "lyrics.ass",
    "lyrics.elrc",
    "lyrics.json",
    "lyrics.lrc",
    "lyrics.manual.lrc",
    "mtv.mp4",
    "original.mp3",
    "skeleton.json",
)


def media_rev(song_id: str) -> str:
    folder = MEDIA_DIR / str(song_id)
    digest = hashlib.sha256()
    found = False
    if folder.is_dir():
        for name in _MEDIA_REV_NAMES:
            path = folder / name
            if not path.is_file():
                continue
            found = True
            stat = path.stat()
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
            digest.update(b"\0")
    if found:
        return digest.hexdigest()[:12]
    marker = folder / "oss.json"
    if marker.is_file():
        try:
            return str(json.loads(marker.read_text(encoding="utf-8")).get("media_rev") or "")
        except (OSError, json.JSONDecodeError, TypeError):
            return ""
    return ""


def media_flags(song_id: str) -> dict[str, Any]:
    folder = MEDIA_DIR / str(song_id)
    native = False
    lyrics_path = folder / "lyrics.json"
    if lyrics_path.exists():
        try:
            lyrics = json.loads(lyrics_path.read_text(encoding="utf-8"))
            native = lyrics.get("native_video") is True
        except (OSError, json.JSONDecodeError):
            native = False
    if not native:
        skeleton_path = folder / "skeleton.json"
        if skeleton_path.exists():
            try:
                skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
                native = bool(skeleton.get("has_video"))
            except (OSError, json.JSONDecodeError):
                native = False
    if not native:
        native = (folder / "mugen.mp4").exists() or (folder / "mugen.webm").exists()
    flags: dict[str, Any] = {"native_video": native}
    rev = media_rev(song_id)
    if rev:
        flags["media_rev"] = rev
    return flags


def with_media_flags(song: dict[str, Any] | None) -> dict[str, Any] | None:
    if not song:
        return song
    song_id = str(song.get("song_id") or song.get("id") or "")
    if not song_id:
        return song
    return {**song, **media_flags(song_id)}


def list_songs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = execute(conn, "SELECT * FROM songs ORDER BY created_at DESC").fetchall()
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
        count = _count_value(execute(conn, "SELECT COUNT(*) FROM queue WHERE room=?", (room["code"],)).fetchone())
        if count <= 0:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (room["code"],))
        elif int(room["now_index"]) < 0:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (room["code"],))
        elif int(room["now_index"]) >= count:
            execute(conn, "UPDATE rooms SET now_index=? WHERE code=?", (count - 1, room["code"]))


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


def ensure_room(code: str | None = None) -> dict[str, Any]:
    if not code:
        code = uuid.uuid4().hex[:6].upper()
    with _LOCK, connect() as conn:
        row = execute(conn, "SELECT * FROM rooms WHERE code=?", (code,)).fetchone()
        if not row:
            execute(conn, "INSERT INTO rooms (code, created_at) VALUES (?,?)", (code, now_ms()))
            row = execute(conn, "SELECT * FROM rooms WHERE code=?", (code,)).fetchone()
    return dict(row)


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


def room_for_hosts(keys: list[str]) -> str:
    for key in keys:
        if not key:
            continue
        with connect() as conn:
            row = execute(conn, "SELECT room FROM hosts WHERE key=?", (key,)).fetchone()
        if row and row["room"]:
            return str(row["room"]).upper()
    return ""


def remember_host_room(keys: list[str], room: str, ua: str = "") -> None:
    code = str(room or "").strip().upper()
    if not code or not keys:
        return
    now = now_ms()
    ua_n = " ".join(str(ua or "").split())[:240]
    with _LOCK, connect() as conn:
        for key in keys:
            if not key:
                continue
            row = execute(conn, "SELECT key FROM hosts WHERE key=?", (key,)).fetchone()
            if row:
                execute(conn, "UPDATE hosts SET room=?, ua=?, last_seen=? WHERE key=?", (code, ua_n, now, key))
            else:
                execute(
                    conn,
                    "INSERT INTO hosts (key, room, ua, created_at, last_seen) VALUES (?,?,?,?,?)",
                    (key, code, ua_n, now, now),
                )


def ensure_room_for_host(keys: list[str], ua: str = "") -> dict[str, Any]:
    room = ensure_room(room_for_hosts(keys) or None)
    remember_host_room(keys, room["code"], ua)
    return room


def room_snapshot(code: str) -> dict[str, Any]:
    room = ensure_room(code)
    with connect() as conn:
        rows = execute(
            conn,
            """
            SELECT queue.id, queue.song_id, queue.position, songs.title, songs.artist, songs.status, songs.language
            FROM queue JOIN songs ON songs.id = queue.song_id
            WHERE queue.room=? ORDER BY queue.position ASC, queue.created_at ASC
            """,
            (code,),
        ).fetchall()
    queue = [dict(row) for row in rows]
    index = int(room["now_index"])
    if queue and index < 0:
        with _LOCK, connect() as conn:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (code,))
        index = 0
        room["now_index"] = 0
    now = queue[index] if queue and 0 <= index < len(queue) else None
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
        pos = _count_value(execute(conn, "SELECT COALESCE(MAX(position),0)+1 FROM queue WHERE room=?", (code,)).fetchone())
        execute(
            conn,
            "INSERT INTO queue (id, room, song_id, position, created_at) VALUES (?,?,?,?,?)",
            (new_id(), code, song_id, pos, now_ms()),
        )
        if not had_playing:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (code,))
    return room_snapshot(code)


def bump(code: str, item_id: str) -> dict[str, Any]:
    snap = room_snapshot(code)
    items = snap["queue"]
    idx = next((i for i, item in enumerate(items) if item["id"] == item_id), None)
    if idx is None or idx <= snap["now_index"] + 1:
        return snap
    target_pos = items[snap["now_index"] + 1]["position"] if len(items) > snap["now_index"] + 1 else items[idx]["position"]
    with _LOCK, connect() as conn:
        execute(conn, "UPDATE queue SET position=? WHERE id=?", (target_pos - 1, item_id))
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
        execute(conn, "DELETE FROM queue WHERE id=?", (item_id,))
        execute(conn, "UPDATE rooms SET now_index=?, paused=0 WHERE code=?", (nxt, code))
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
        execute(conn, "UPDATE rooms SET now_index=?, paused=0 WHERE code=?", (idx, code))
    return room_snapshot(code)


def set_mix(
    code: str,
    vocal_mix: float | None = None,
    volume: int | None = None,
    mic_gain: int | None = None,
    lyric_mode: str | None = None,
    paused: bool | None = None,
) -> dict[str, Any]:
    fields = {}
    if vocal_mix is not None:
        fields["vocal_mix"] = max(0.0, min(1.0, float(vocal_mix)))
    if volume is not None:
        fields["volume"] = max(0, min(100, int(volume)))
    if mic_gain is not None:
        fields["mic_gain"] = max(0, min(100, int(mic_gain)))
    if lyric_mode is not None:
        fields["lyric_mode"] = normalize_lyric_mode(lyric_mode)
    if paused is not None:
        fields["paused"] = 1 if paused else 0
    allowed = {key: value for key, value in fields.items() if key in ROOM_FIELDS}
    if allowed:
        assignments = ", ".join(f"{key}=?" for key in allowed)
        with _LOCK, connect() as conn:
            execute(conn, f"UPDATE rooms SET {assignments} WHERE code=?", (*allowed.values(), code))
    return room_snapshot(code)


def write_json(path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _user_row(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    user_id = str(data["id"])
    return {
        "id": user_id,
        "sid": user_id[:6].upper(),
        "nickname": data.get("nickname") or f"ID {user_id[:6].upper()}",
        "avatar": data.get("avatar") or "",
        "wechat": bool(data.get("wechat_openid")),
    }


def get_user(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = execute(conn, "SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_row(row)


def upsert_wechat_user(openid: str, unionid: str = "", nickname: str = "", avatar: str = "") -> dict[str, Any]:
    openid = (openid or "").strip()
    if not openid:
        raise ValueError("微信未返回账号")
    now = now_ms()
    with _LOCK, connect() as conn:
        row = execute(conn, "SELECT * FROM users WHERE wechat_openid=?", (openid,)).fetchone()
        if row:
            user_id = row["id"]
            execute(
                conn,
                "UPDATE users SET wechat_unionid=?, nickname=?, avatar=? WHERE id=?",
                (unionid or row["wechat_unionid"], nickname or row["nickname"], avatar or row["avatar"], user_id),
            )
        else:
            user_id = new_id()
            execute(
                conn,
                "INSERT INTO users (id, wechat_openid, wechat_unionid, nickname, avatar, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, openid, unionid, nickname or f"ID {user_id[:6].upper()}", avatar, now),
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
        row = execute(conn, "SELECT * FROM users WHERE device_id=?", (device_id,)).fetchone()
        if row:
            user_id = row["id"]
            if nickname and nickname != row["nickname"]:
                execute(conn, "UPDATE users SET nickname=? WHERE id=?", (nickname, user_id))
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
        row = execute(conn, "SELECT * FROM login_tickets WHERE id=?", (ticket,)).fetchone()
    if not row:
        return None
    data = dict(row)
    if data["status"] == "pending" and int(data["expires_at"]) <= now_ms():
        with _LOCK, connect() as conn:
            execute(conn, "UPDATE login_tickets SET status='expired' WHERE id=? AND status='pending'", (ticket,))
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
