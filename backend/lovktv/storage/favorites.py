"""Per-owner song favourites used by the phone listening catalogue."""

from __future__ import annotations

import threading

from lovktv.core.db import execute
from lovktv.storage.store import connect, now_ms

_LOCK = threading.Lock()


def list_favorite_ids(owner: str) -> set[str]:
    owner = str(owner or "").strip()
    if not owner:
        return set()
    with connect() as conn:
        rows = execute(
            conn, "SELECT song_id FROM song_favorites WHERE owner=?", (owner,)
        ).fetchall()
    return {str(row[0] if not isinstance(row, dict) else row["song_id"]) for row in rows}


def is_favorite(owner: str, song_id: str) -> bool:
    owner = str(owner or "").strip()
    song_id = str(song_id or "").strip()
    if not owner or not song_id:
        return False
    with connect() as conn:
        row = execute(
            conn,
            "SELECT 1 FROM song_favorites WHERE owner=? AND song_id=?",
            (owner, song_id),
        ).fetchone()
    return row is not None


def set_favorite(owner: str, song_id: str, favorite: bool = True) -> bool:
    owner = str(owner or "").strip()
    song_id = str(song_id or "").strip()
    if not owner or not song_id:
        return False
    with _LOCK, connect() as conn:
        if favorite:
            execute(
                conn,
                "INSERT INTO song_favorites (owner, song_id, created_at) VALUES (?,?,?) "
                "ON CONFLICT (owner, song_id) DO NOTHING",
                (owner, song_id, now_ms()),
            )
        else:
            execute(
                conn,
                "DELETE FROM song_favorites WHERE owner=? AND song_id=?",
                (owner, song_id),
            )
    return favorite


def delete_song_favorites(song_id: str) -> None:
    song_id = str(song_id or "").strip()
    if not song_id:
        return
    with _LOCK, connect() as conn:
        execute(conn, "DELETE FROM song_favorites WHERE song_id=?", (song_id,))


def merge_owners(source: str, destination: str) -> None:
    """Move guest saves onto a newly-created account without duplicates."""
    source = str(source or "").strip()
    destination = str(destination or "").strip()
    if not source or not destination or source == destination:
        return
    with _LOCK, connect() as conn:
        execute(
            conn,
            "INSERT INTO song_favorites (owner, song_id, created_at) "
            "SELECT ?, song_id, created_at FROM song_favorites WHERE owner=? "
            "ON CONFLICT (owner, song_id) DO NOTHING",
            (destination, source),
        )
        execute(conn, "DELETE FROM song_favorites WHERE owner=?", (source,))
