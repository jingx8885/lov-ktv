"""Leitner-box scheduling shared by the word deck and the mistake deck.

Pure functions only — no DB, no clock. Callers pass `now` in epoch ms so the
same helpers drive both storage layers and stay trivially testable.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

DAY_MS = 86_400_000

# Box 0 is "same session again"; a card retires once it clears box 5.
INTERVALS = (0, 1, 2, 4, 8, 16)
MAX_STAGE = len(INTERVALS)

# A miss drops two boxes rather than resetting to zero: a word the user has
# seen eight times but slipped on today does not deserve the same runway as a
# word met for the first time.
LAPSE_DROP = 2


def clamp_stage(stage: int) -> int:
    try:
        value = int(stage)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_STAGE, value))


def is_retired(stage: int) -> bool:
    return clamp_stage(stage) >= MAX_STAGE


def schedule(stage: int, ok: bool, now: int | None = None) -> dict[str, int]:
    """Advance or drop a card's box and return its next `stage` / `due_at`.

    A miss comes due immediately, not after the box's interval: the user just
    proved they cannot recall it, so it belongs in today's queue again even
    though the box it fell into would otherwise buy it a day or two.

    `retired_at` is non-zero once the card has cleared the last box; the deck
    keeps showing it in the list but never queues it again.
    """
    moment = int(now if now is not None else time.time() * 1000)
    current = clamp_stage(stage)
    if not ok:
        return {"stage": max(0, current - LAPSE_DROP), "due_at": moment, "retired_at": 0}
    nxt = min(MAX_STAGE, current + 1)
    if nxt >= MAX_STAGE:
        return {"stage": MAX_STAGE, "due_at": 0, "retired_at": moment}
    return {
        "stage": nxt,
        "due_at": moment + INTERVALS[nxt] * DAY_MS,
        "retired_at": 0,
    }


def day_key(ms: int | None = None) -> str:
    """`YYYY-MM-DD` for a streak row. UTC keeps the key stable across hosts."""
    moment = int(ms if ms is not None else time.time() * 1000)
    return datetime.fromtimestamp(moment / 1000, timezone.utc).strftime("%Y-%m-%d")


def end_of_day(ms: int | None = None) -> int:
    """Last millisecond of the UTC day holding `ms`.

    Anything due before this counts as "due today", so a card scheduled for
    later this evening still shows up in the morning session.
    """
    moment = int(ms if ms is not None else time.time() * 1000)
    start = datetime.fromtimestamp(moment / 1000, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((start + timedelta(days=1)).timestamp() * 1000) - 1


def streak_from_days(days: list[str], today: str | None = None) -> int:
    """Consecutive days ending today (or yesterday, if today is not done yet).

    Counting from yesterday matters: opening the app at 9am should still read
    "3 days" rather than dropping to 0 before the day's session is finished.
    """
    marked = {str(day) for day in days if day}
    if not marked:
        return 0
    cursor = datetime.strptime(today or day_key(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if cursor.strftime("%Y-%m-%d") not in marked:
        cursor -= timedelta(days=1)
    count = 0
    while cursor.strftime("%Y-%m-%d") in marked:
        count += 1
        cursor -= timedelta(days=1)
    return count
