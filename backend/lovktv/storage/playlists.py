"""Per-owner named playlists; the phone listen page treats each list as a catalog."""

from __future__ import annotations

import threading
import uuid

from lovktv.core.db import execute
from lovktv.storage.store import connect, now_ms

_LOCK = threading.Lock()
NAME_MAX = 24
LIST_MAX = 50


def _new_id() -> str:
    return "pl" + uuid.uuid4().hex[:10]


def _row_dict(row) -> dict:
    if isinstance(row, dict):
        return dict(row)
    return {k: row[k] for k in row.keys()}


def _playlist_row(row) -> dict:
    data = _row_dict(row)
    return {
        "id": str(data.get("id") or ""),
        "name": str(data.get("name") or ""),
        "created_at": int(data.get("created_at") or 0),
        "updated_at": int(data.get("updated_at") or 0),
        "count": int(data.get("count") or 0),
    }


def list_playlists(owner: str, song_id: str = "") -> list[dict]:
    """Newest first; has_song marks lists that already contain song_id."""
    owner = str(owner or "").strip()
    if not owner:
        return []
    song_id = str(song_id or "").strip()
    sql = """
        SELECT p.id, p.name, p.created_at, p.updated_at,
               COUNT(i.song_id) AS count,
               SUM(CASE WHEN i.song_id = ? THEN 1 ELSE 0 END) AS has_song
        FROM playlists p
        LEFT JOIN playlist_items i ON i.playlist_id = p.id
        WHERE p.owner = ?
        GROUP BY p.id, p.name, p.created_at, p.updated_at
        ORDER BY p.created_at DESC, p.name
    """
    with connect() as conn:
        rows = execute(conn, sql, (song_id, owner)).fetchall()
    out = []
    for row in rows:
        item = _playlist_row(row)
        item["has_song"] = bool(_row_dict(row).get("has_song"))
        out.append(item)
    return out


def playlist_count(owner: str) -> int:
    owner = str(owner or "").strip()
    if not owner:
        return 0
    with connect() as conn:
        row = execute(
            conn, "SELECT COUNT(*) AS count FROM playlists WHERE owner=?", (owner,)
        ).fetchone()
    data = _row_dict(row) if row else {}
    return int(data.get("count") or 0)


def get_playlist(owner: str, playlist_id: str) -> dict | None:
    owner = str(owner or "").strip()
    playlist_id = str(playlist_id or "").strip()
    if not owner or not playlist_id:
        return None
    with connect() as conn:
        row = execute(
            conn,
            "SELECT id, name, created_at, updated_at, 0 AS count "
            "FROM playlists WHERE id=? AND owner=?",
            (playlist_id, owner),
        ).fetchone()
        if not row:
            return None
        item = _playlist_row(row)
        cnt = execute(
            conn,
            "SELECT COUNT(*) AS count FROM playlist_items WHERE playlist_id=?",
            (playlist_id,),
        ).fetchone()
    item["count"] = int(_row_dict(cnt).get("count") or 0) if cnt else 0
    return item


def name_taken(owner: str, name: str, exclude_id: str = "") -> bool:
    owner = str(owner or "").strip()
    name = str(name or "").strip()
    if not owner or not name:
        return False
    with connect() as conn:
        rows = execute(
            conn, "SELECT id, name FROM playlists WHERE owner=?", (owner,)
        ).fetchall()
    for row in rows:
        data = _row_dict(row)
        if str(data.get("id") or "") == exclude_id:
            continue
        if str(data.get("name") or "") == name:
            return True
    return False


def create_playlist(owner: str, name: str) -> dict:
    owner = str(owner or "").strip()
    name = str(name or "").strip()
    if not owner or not name:
        return {}
    playlist_id = _new_id()
    with _LOCK, connect() as conn:
        # Millisecond timestamps can tie on back-to-back inserts; keep the
        # newest-first ordering deterministic by nudging past the max.
        last = execute(
            conn, "SELECT MAX(created_at) AS m FROM playlists WHERE owner=?", (owner,)
        ).fetchone()
        last_ms = int((_row_dict(last).get("m") if last else 0) or 0)
        now = max(now_ms(), last_ms + 1)
        execute(
            conn,
            "INSERT INTO playlists (id, owner, name, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (playlist_id, owner, name, now, now),
        )
    return {
        "id": playlist_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "count": 0,
    }


def rename_playlist(owner: str, playlist_id: str, name: str) -> bool:
    name = str(name or "").strip()
    if not name:
        return False
    with _LOCK, connect() as conn:
        cur = execute(
            conn,
            "UPDATE playlists SET name=?, updated_at=? WHERE id=? AND owner=?",
            (name, now_ms(), str(playlist_id or "").strip(), str(owner or "").strip()),
        )
    return getattr(cur, "rowcount", 0) > 0


def delete_playlist(owner: str, playlist_id: str) -> bool:
    owner = str(owner or "").strip()
    playlist_id = str(playlist_id or "").strip()
    if not owner or not playlist_id:
        return False
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT id FROM playlists WHERE id=? AND owner=?",
            (playlist_id, owner),
        ).fetchone()
        if not row:
            return False
        execute(conn, "DELETE FROM playlist_items WHERE playlist_id=?", (playlist_id,))
        execute(conn, "DELETE FROM playlists WHERE id=?", (playlist_id,))
    return True


def playlist_song_ids(playlist_id: str) -> list[str]:
    playlist_id = str(playlist_id or "").strip()
    if not playlist_id:
        return []
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT song_id FROM playlist_items WHERE playlist_id=? "
            "ORDER BY position, created_at, song_id",
            (playlist_id,),
        ).fetchall()
    return [str(_row_dict(row).get("song_id") or "") for row in rows]


def _next_position(conn, playlist_id: str) -> int:
    row = execute(
        conn,
        "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM playlist_items "
        "WHERE playlist_id=?",
        (playlist_id,),
    ).fetchone()
    data = _row_dict(row) if row else {}
    return int(data.get("next") or 0)


def add_song(owner: str, playlist_id: str, song_id: str) -> bool:
    """Insert at the end; duplicates are a no-op that still reports success."""
    owner = str(owner or "").strip()
    playlist_id = str(playlist_id or "").strip()
    song_id = str(song_id or "").strip()
    if not owner or not playlist_id or not song_id:
        return False
    if not get_playlist(owner, playlist_id):
        return False
    with _LOCK, connect() as conn:
        position = _next_position(conn, playlist_id)
        execute(
            conn,
            "INSERT INTO playlist_items (playlist_id, song_id, position, created_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT (playlist_id, song_id) DO NOTHING",
            (playlist_id, song_id, position, now_ms()),
        )
        execute(
            conn,
            "UPDATE playlists SET updated_at=? WHERE id=?",
            (now_ms(), playlist_id),
        )
    return True


def remove_song(owner: str, playlist_id: str, song_id: str) -> bool:
    owner = str(owner or "").strip()
    playlist_id = str(playlist_id or "").strip()
    song_id = str(song_id or "").strip()
    if not owner or not playlist_id or not song_id:
        return False
    with _LOCK, connect() as conn:
        cur = execute(
            conn,
            "DELETE FROM playlist_items WHERE playlist_id=? AND song_id=? AND "
            "playlist_id IN (SELECT id FROM playlists WHERE id=? AND owner=?)",
            (playlist_id, song_id, playlist_id, owner),
        )
    return getattr(cur, "rowcount", 0) > 0


def remove_song_everywhere(song_id: str) -> None:
    """Called when a song leaves the shared library."""
    song_id = str(song_id or "").strip()
    if not song_id:
        return
    with _LOCK, connect() as conn:
        execute(conn, "DELETE FROM playlist_items WHERE song_id=?", (song_id,))


def _unique_name(conn, owner: str, name: str) -> str:
    rows = execute(
        conn, "SELECT name FROM playlists WHERE owner=?", (owner,)
    ).fetchall()
    taken = {str(_row_dict(row).get("name") or "") for row in rows}
    if name not in taken:
        return name
    for n in range(2, 100):
        cand = f"{name} ({n})"
        if cand not in taken:
            return cand
    return f"{name} ({now_ms()})"


def merge_owners(source: str, destination: str) -> None:
    """Move guest lists onto a newly-created account without losing tracks."""
    source = str(source or "").strip()
    destination = str(destination or "").strip()
    if not source or not destination or source == destination:
        return
    with _LOCK, connect() as conn:
        rows = execute(
            conn,
            "SELECT id, name, created_at FROM playlists WHERE owner=? "
            "ORDER BY created_at, id",
            (source,),
        ).fetchall()
        for row in rows:
            data = _row_dict(row)
            pid = str(data.get("id") or "")
            # Re-own in place so playlist_items rows keep pointing at the list;
            # only the name may need a suffix when the account already owns
            # one with the same title.
            name = _unique_name(conn, destination, str(data.get("name") or ""))
            execute(
                conn,
                "UPDATE playlists SET owner=?, name=?, updated_at=? WHERE id=?",
                (destination, name, now_ms(), pid),
            )
