"""Permission for song reprocessing from the phone desk."""

from __future__ import annotations

SONG_ADMIN_USERNAME = "jingxu8885"
SONG_ADMIN_EMAIL = "jingxu8885@gmail.com"


def is_unrestricted_admin(user: dict | None) -> bool:
    """Return whether an account has the built-in unlimited admin entitlement.

    The username covers the existing password account while the email also
    covers the same person signing in through Google.  Keep this check in one
    place so billing, quota, rooms and queue scheduling cannot drift apart.
    """
    account = user or {}
    username = str(account.get("username") or "").strip()
    email = str(account.get("email") or "").strip()
    return bool(
        (username and username.casefold() == SONG_ADMIN_USERNAME.casefold())
        or (email and email.casefold() == SONG_ADMIN_EMAIL.casefold())
    )


def is_song_admin(user: dict | None) -> bool:
    """Return whether a signed-in account may reprocess song lyrics."""
    return is_unrestricted_admin(user)
