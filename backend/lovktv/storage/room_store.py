"""SQLite persistence for karaoke rooms and LAN host metadata."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Protocol
from urllib.parse import urlparse

from lovktv.core.db import connect as db_connect
from lovktv.core.db import execute
from lovktv.core.schema import ROOM_FIELDS

_LOCK = threading.Lock()


class RoomRepository(Protocol):
    def room_snapshot(self, code: str) -> dict[str, Any]: ...
    def enqueue(self, code: str, song_id: str) -> dict[str, Any]: ...
    def bump(self, code: str, item_id: str) -> dict[str, Any]: ...
    def skip(self, code: str) -> dict[str, Any]: ...
    def play_now(
        self, code: str, item_id: str = "", song_id: str = ""
    ) -> dict[str, Any]: ...
    def set_mix(
        self,
        code: str,
        vocal_mix: float | None = None,
        volume: int | None = None,
        mic_gain: int | None = None,
        lyric_mode: str | None = None,
        paused: bool | None = None,
    ) -> dict[str, Any]: ...
    def set_room_lan(
        self,
        code: str,
        origin: str,
        mic_port: int | None = None,
        mic_sample_rate: int | None = None,
    ) -> dict[str, Any]: ...


def connect():
    # Read the legacy module's mutable path so tests and runtime reconfiguration
    # use the same database while the physical room SQL lives here.
    from lovktv.storage import store

    return db_connect(store.DB_PATH)


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _count_value(row: Any) -> int:
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def ensure_room(code: str | None = None) -> dict[str, Any]:
    code = str(code or uuid.uuid4().hex[:6]).upper()
    with _LOCK, connect() as conn:
        row = execute(conn, "SELECT * FROM rooms WHERE code=?", (code,)).fetchone()
        if not row:
            execute(
                conn,
                "INSERT INTO rooms (code, created_at) VALUES (?,?)",
                (code, now_ms()),
            )
            row = execute(conn, "SELECT * FROM rooms WHERE code=?", (code,)).fetchone()
    return dict(row)


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
                execute(
                    conn,
                    "UPDATE hosts SET room=?, ua=?, last_seen=? WHERE key=?",
                    (code, ua_n, now, key),
                )
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


def _private_ipv4(host: str) -> bool:
    name = str(host or "").strip().lower()
    if name == "localhost" or name.endswith(".local"):
        return True
    parts = name.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(part) for part in parts]
    except ValueError:
        return False
    return all(0 <= n <= 255 for n in nums) and (
        nums[0] == 10
        or (nums[0] == 192 and nums[1] == 168)
        or (nums[0] == 172 and 16 <= nums[1] <= 31)
    )


def normalize_lan_origin(raw: str) -> str:
    text = str(raw or "").strip().rstrip("/")
    if not text:
        raise ValueError("局域网地址无效")
    if "://" not in text:
        text = "http://" + text
    parsed = urlparse(text)
    if parsed.scheme != "http" or not _private_ipv4(parsed.hostname or ""):
        raise ValueError("局域网地址无效")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("局域网地址无效")
    if parsed.username or parsed.password:
        raise ValueError("局域网地址无效")
    port = parsed.port or 80
    if not 1 <= port <= 65535:
        raise ValueError("局域网地址无效")
    return f"http://{parsed.hostname}:{port}"


def room_snapshot(code: str) -> dict[str, Any]:
    code = str(code or "").upper()
    room = ensure_room(code)
    with connect() as conn:
        rows = execute(
            conn,
            """SELECT queue.id, queue.song_id, queue.position,
            songs.title, songs.artist, songs.status, songs.language
            FROM queue JOIN songs ON songs.id=queue.song_id
            WHERE queue.room=? ORDER BY queue.position ASC, queue.created_at ASC""",
            (code,),
        ).fetchall()
    items = [dict(row) for row in rows]
    index = int(room["now_index"])
    if items and index < 0:
        with _LOCK, connect() as conn:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (code,))
        index = 0
        room["now_index"] = 0
    return {
        **room,
        "queue": items,
        "now_playing": items[index] if items and 0 <= index < len(items) else None,
    }


def _song(song_id: str) -> dict[str, Any] | None:
    from lovktv.storage.store import get_song

    return get_song(song_id)


def enqueue(code: str, song_id: str) -> dict[str, Any]:
    code = code.upper()
    ensure_room(code)
    song = _song(song_id)
    if not song or song.get("status") != "ready":
        raise ValueError("这首还没就绪，不能点")
    snap = room_snapshot(code)
    if any(item["song_id"] == song_id for item in snap["queue"]):
        return snap
    with _LOCK, connect() as conn:
        pos = _count_value(
            execute(
                conn,
                "SELECT COALESCE(MAX(position),0)+1 FROM queue WHERE room=?",
                (code,),
            ).fetchone()
        )
        execute(
            conn,
            "INSERT INTO queue (id,room,song_id,position,created_at) VALUES (?,?,?,?,?)",
            (new_id(), code, song_id, pos, now_ms()),
        )
        if snap.get("now_playing") is None:
            execute(conn, "UPDATE rooms SET now_index=0 WHERE code=?", (code,))
    return room_snapshot(code)


def bump(code: str, item_id: str) -> dict[str, Any]:
    code = str(code or "").upper()
    snap = room_snapshot(code)
    items = list(snap["queue"])
    idx = next((i for i, item in enumerate(items) if item["id"] == item_id), None)
    if idx is None or idx <= snap["now_index"] + 1:
        return snap
    item = items.pop(idx)
    items.insert(int(snap["now_index"]) + 1, item)
    with _LOCK, connect() as conn:
        for position, row in enumerate(items, start=1):
            execute(conn, "UPDATE queue SET position=? WHERE id=?", (position, row["id"]))
    return room_snapshot(code)


def skip(code: str) -> dict[str, Any]:
    code = code.upper()
    snap = room_snapshot(code)
    items = snap["queue"]
    if not items or snap.get("now_playing") is None:
        return snap
    cur = max(0, min(snap["now_index"], len(items) - 1))
    remaining = len(items) - 1
    nxt = 0 if remaining <= 0 or cur >= remaining else cur
    with _LOCK, connect() as conn:
        execute(conn, "DELETE FROM queue WHERE id=?", (items[cur]["id"],))
        execute(
            conn, "UPDATE rooms SET now_index=?, paused=0 WHERE code=?", (nxt, code)
        )
    return room_snapshot(code)


def play_now(code: str, item_id: str = "", song_id: str = "") -> dict[str, Any]:
    code = code.upper()
    if song_id and not item_id:
        snap = room_snapshot(code)
        if snap.get("now_playing"):
            enqueue(code, song_id)
            return room_snapshot(code)
        existing = next(
            (item for item in snap["queue"] if item["song_id"] == song_id), None
        )
        if existing is None:
            song = _song(song_id)
            if not song or song.get("status") != "ready":
                raise ValueError("这首还没就绪，不能点")
            enqueue(code, song_id)
            snap = room_snapshot(code)
            existing = next(
                (item for item in snap["queue"] if item["song_id"] == song_id), None
            )
        item_id = existing["id"] if existing else ""
    snap = room_snapshot(code)
    idx = next(
        (i for i, item in enumerate(snap["queue"]) if item["id"] == item_id), None
    )
    if idx is None:
        return snap
    if snap["queue"][idx].get("status") != "ready":
        raise ValueError("这首还没就绪，不能点")
    with _LOCK, connect() as conn:
        execute(
            conn, "UPDATE rooms SET now_index=?, paused=0 WHERE code=?", (idx, code)
        )
    return room_snapshot(code)


def set_mix(
    code: str,
    vocal_mix: float | None = None,
    volume: int | None = None,
    mic_gain: int | None = None,
    lyric_mode: str | None = None,
    paused: bool | None = None,
) -> dict[str, Any]:
    from lovktv.storage.store import normalize_lyric_mode

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
            execute(
                conn,
                f"UPDATE rooms SET {assignments} WHERE code=?",
                (*allowed.values(), code.upper()),
            )
    return room_snapshot(code)


def set_room_lan(
    code: str,
    origin: str,
    mic_port: int | None = None,
    mic_sample_rate: int | None = None,
) -> dict[str, Any]:
    room = str(code or "").strip().upper()
    lan = normalize_lan_origin(origin)
    port = int(mic_port or 0)
    if port < 0 or port > 65535:
        port = 0
    rate = int(mic_sample_rate or 48000)
    if rate < 8000 or rate > 96000:
        rate = 48000
    ensure_room(room)
    with _LOCK, connect() as conn:
        execute(
            conn,
            "UPDATE rooms SET lan_origin=?,lan_mic_port=?,lan_mic_sample_rate=?,lan_seen_at=? WHERE code=?",
            (lan, port, rate, now_ms(), room),
        )
    return room_snapshot(room)


class SqliteRoomStore:
    room_snapshot = staticmethod(room_snapshot)
    enqueue = staticmethod(enqueue)
    bump = staticmethod(bump)
    skip = staticmethod(skip)
    play_now = staticmethod(play_now)
    set_mix = staticmethod(set_mix)
    set_room_lan = staticmethod(set_room_lan)
