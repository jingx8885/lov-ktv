"""Word-deck cards and the per-deck daily check-in.

Mistake cards live in `learn_mistakes` (see `lovktv.storage.learn`) so the
in-song review path keeps writing one row; only collected words get their own
table here.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

from lovktv.core.db import execute
from lovktv.storage.store import connect, now_ms
from lovktv.workers import srs

DECKS = ("word", "mistake")
MAX_CARDS = 2000
_LOCK = threading.Lock()

_FIELDS = (
    "song_id",
    "song_title",
    "item_key",
    "text",
    "zh",
    "romaji",
    "line_text",
)


def _rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def card_id(song_id: str, item_key: str) -> str:
    """Stable id so re-collecting the same word never forks a second card."""
    raw = f"{str(song_id or '').strip()}:{str(item_key or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _clean(card: dict[str, Any]) -> dict[str, Any]:
    out = {name: str(card.get(name) or "").strip()[:400] for name in _FIELDS}
    for name in ("start_ms", "end_ms"):
        try:
            out[name] = max(0, int(card.get(name) or 0))
        except (TypeError, ValueError):
            out[name] = 0
    if not out["item_key"]:
        out["item_key"] = out["text"]
    return out


def upsert_card(owner: str, card: dict[str, Any]) -> dict[str, Any]:
    """Create a card, or refresh the wording of one already collected.

    Scheduling state is never touched on re-collect — a user who taps the same
    word again in the lyrics should not have their progress on it reset.
    """
    saved, _created = _upsert(owner, card)
    return saved


def _upsert(owner: str, card: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    owner = str(owner or "").strip()
    body = _clean(card if isinstance(card, dict) else {})
    if not owner or not body["text"]:
        return {}, False
    cid = card_id(body["song_id"], body["item_key"])
    now = now_ms()
    with _LOCK, connect() as conn:
        prev = execute(
            conn,
            "SELECT * FROM learn_cards WHERE owner=? AND card_id=?",
            (owner, cid),
        ).fetchone()
        if prev:
            execute(
                conn,
                "UPDATE learn_cards SET song_title=?, text=?, zh=?, romaji=?, line_text=?, "
                "start_ms=?, end_ms=? WHERE owner=? AND card_id=?",
                (
                    body["song_title"],
                    body["text"],
                    body["zh"],
                    body["romaji"],
                    body["line_text"],
                    body["start_ms"],
                    body["end_ms"],
                    owner,
                    cid,
                ),
            )
        else:
            total = execute(
                conn, "SELECT COUNT(*) AS n FROM learn_cards WHERE owner=?", (owner,)
            ).fetchone()
            if int(dict(total).get("n") or 0) >= MAX_CARDS:
                return {}, False
            execute(
                conn,
                "INSERT INTO learn_cards (owner, card_id, song_id, song_title, item_key, "
                "text, zh, romaji, line_text, start_ms, end_ms, stage, reps, lapses, "
                "due_at, last_at, created_at, retired_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,0,0,0,?,0,?,0)",
                (
                    owner,
                    cid,
                    body["song_id"],
                    body["song_title"],
                    body["item_key"],
                    body["text"],
                    body["zh"],
                    body["romaji"],
                    body["line_text"],
                    body["start_ms"],
                    body["end_ms"],
                    now,
                    now,
                ),
            )
        saved = execute(
            conn,
            "SELECT * FROM learn_cards WHERE owner=? AND card_id=?",
            (owner, cid),
        ).fetchone()
    return (dict(saved) if saved else {}), not prev


def import_cards(owner: str, cards: list[Any]) -> dict[str, int]:
    """Bulk-migrate the browser's localStorage list. Idempotent by card_id."""
    added = 0
    seen = 0
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        seen += 1
        _saved, created = _upsert(owner, card)
        if created:
            added += 1
    return {"seen": seen, "added": added, "total": count_cards(owner)}


def get_card(owner: str, cid: str) -> dict[str, Any]:
    if not owner or not cid:
        return {}
    with connect() as conn:
        row = execute(
            conn, "SELECT * FROM learn_cards WHERE owner=? AND card_id=?", (owner, cid)
        ).fetchone()
    return dict(row) if row else {}


def list_cards(owner: str, limit: int = 500) -> list[dict[str, Any]]:
    if not owner:
        return []
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM learn_cards WHERE owner=? ORDER BY created_at DESC LIMIT ?",
            (owner, max(1, min(MAX_CARDS, int(limit or 500)))),
        ).fetchall()
    return _rows(rows)


def count_cards(owner: str) -> int:
    if not owner:
        return 0
    with connect() as conn:
        row = execute(
            conn, "SELECT COUNT(*) AS n FROM learn_cards WHERE owner=?", (owner,)
        ).fetchone()
    return int(dict(row).get("n") or 0) if row else 0


def due_cards(owner: str, limit: int, now: int | None = None) -> list[dict[str, Any]]:
    """Cards due today, oldest-due first; never returns retired ones."""
    if not owner:
        return []
    cutoff = srs.end_of_day(now)
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM learn_cards WHERE owner=? AND retired_at=0 AND due_at<=? "
            "ORDER BY due_at, created_at LIMIT ?",
            (owner, cutoff, max(1, int(limit or 10))),
        ).fetchall()
    return _rows(rows)


def bump_card(owner: str, cid: str, ok: bool, now: int | None = None) -> dict[str, Any]:
    moment = int(now if now is not None else now_ms())
    prev = get_card(owner, cid)
    if not prev:
        return {}
    plan = srs.schedule(int(prev.get("stage") or 0), bool(ok), moment)
    lapses = int(prev.get("lapses") or 0) + (0 if ok else 1)
    with _LOCK, connect() as conn:
        execute(
            conn,
            "UPDATE learn_cards SET stage=?, reps=?, lapses=?, due_at=?, last_at=?, "
            "retired_at=? WHERE owner=? AND card_id=?",
            (
                plan["stage"],
                int(prev.get("reps") or 0) + 1,
                lapses,
                plan["due_at"],
                moment,
                plan["retired_at"],
                owner,
                cid,
            ),
        )
    return get_card(owner, cid)


def delete_card(owner: str, cid: str) -> bool:
    if not owner or not cid:
        return False
    with _LOCK, connect() as conn:
        cur = execute(
            conn, "DELETE FROM learn_cards WHERE owner=? AND card_id=?", (owner, cid)
        )
        removed = int(getattr(cur, "rowcount", 0) or 0)
    return removed > 0


def mark_day(owner: str, deck: str, done: int, now: int | None = None) -> str:
    """Record today's check-in for one deck. Counts accumulate within a day."""
    owner = str(owner or "").strip()
    deck = deck if deck in DECKS else "word"
    if not owner:
        return ""
    moment = int(now if now is not None else now_ms())
    day = srs.day_key(moment)
    delta = max(0, int(done or 0))
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM learn_recite_days WHERE owner=? AND deck=? AND day=?",
            (owner, deck, day),
        ).fetchone()
        if row:
            execute(
                conn,
                "UPDATE learn_recite_days SET done=? WHERE owner=? AND deck=? AND day=?",
                (int(dict(row).get("done") or 0) + delta, owner, deck, day),
            )
        else:
            execute(
                conn,
                "INSERT INTO learn_recite_days (owner, deck, day, done, created_at) VALUES (?,?,?,?,?)",
                (owner, deck, day, delta, moment),
            )
    return day


def list_days(owner: str, deck: str, limit: int = 400) -> list[dict[str, Any]]:
    owner = str(owner or "").strip()
    deck = deck if deck in DECKS else "word"
    if not owner:
        return []
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM learn_recite_days WHERE owner=? AND deck=? ORDER BY day DESC LIMIT ?",
            (owner, deck, max(1, int(limit or 400))),
        ).fetchall()
    return _rows(rows)


def deck_streak(owner: str, deck: str, now: int | None = None) -> dict[str, Any]:
    days = list_days(owner, deck)
    today = srs.day_key(now)
    done_today = next(
        (int(row.get("done") or 0) for row in days if str(row.get("day")) == today), 0
    )
    return {
        "streak": srs.streak_from_days([str(row.get("day")) for row in days], today),
        "today": done_today,
        "day": today,
    }
