"""Permission for song reprocessing from the phone desk."""

from __future__ import annotations

SONG_ADMIN_USERNAME = "jingxu8885"


def is_song_admin(user: dict | None) -> bool:
    """Return whether a signed-in account may reprocess song lyrics."""
    username = str((user or {}).get("username") or "").strip()
    return bool(username) and username.casefold() == SONG_ADMIN_USERNAME.casefold()
