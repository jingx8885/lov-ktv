"""Campaign progress, word/sentence mastery, and the mistake notebook."""

from __future__ import annotations

import json
import threading
from typing import Any

from lovktv.core.db import execute
from lovktv.storage.store import connect, now_ms
from lovktv.workers import srs

MASTERY_STREAK = 2
_LOCK = threading.Lock()


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def _rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def list_progress(owner: str, song_id: str) -> list[dict[str, Any]]:
    if not owner or not song_id:
        return []
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM learn_progress WHERE owner=? AND song_id=? ORDER BY unit_id, skill",
            (owner, song_id),
        ).fetchall()
    return _rows(rows)


def claim_submission(owner: str, song_id: str, attempt_id: str) -> bool:
    """Claim an attempt id exactly once; returns False for a duplicate."""
    owner = str(owner or "").strip()
    song_id = str(song_id or "").strip()
    attempt_id = str(attempt_id or "").strip()
    if not owner or not song_id or not attempt_id or len(attempt_id) > 96:
        return False
    with _LOCK, connect() as conn:
        try:
            execute(
                conn,
                "INSERT INTO learn_submissions (owner, song_id, attempt_id, created_at) VALUES (?,?,?,?)",
                (owner, song_id, attempt_id, now_ms()),
            )
        except Exception:
            # Primary-key conflicts are the expected duplicate path.  The
            # endpoint treats an unclaimable id as a rejected submission.
            return False
    return True


def upsert_progress(
    owner: str,
    song_id: str,
    unit_id: str,
    skill: str,
    *,
    pct: int,
    passed: bool,
) -> dict[str, Any]:
    now = now_ms()
    score = max(0, min(100, int(pct)))
    status = "ready"
    if passed and score >= 90:
        status = "mastered"
    elif passed:
        status = "passed"
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM learn_progress WHERE owner=? AND song_id=? AND unit_id=? AND skill=?",
            (owner, song_id, unit_id, skill),
        ).fetchone()
        prev = _row(row)
        attempts = int(prev["attempts"]) + 1 if prev else 1
        if prev and prev.get("status") == "mastered":
            status = "mastered"
            score = max(score, int(prev.get("score") or 0))
        elif prev and prev.get("status") == "passed" and status == "ready":
            status = "passed"
            score = max(score, int(prev.get("score") or 0))
        if prev:
            execute(
                conn,
                "UPDATE learn_progress SET status=?, score=?, attempts=?, updated_at=? "
                "WHERE owner=? AND song_id=? AND unit_id=? AND skill=?",
                (status, score, attempts, now, owner, song_id, unit_id, skill),
            )
        else:
            execute(
                conn,
                "INSERT INTO learn_progress "
                "(owner, song_id, unit_id, skill, status, score, attempts, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (owner, song_id, unit_id, skill, status, score, attempts, now),
            )
        saved = execute(
            conn,
            "SELECT * FROM learn_progress WHERE owner=? AND song_id=? AND unit_id=? AND skill=?",
            (owner, song_id, unit_id, skill),
        ).fetchone()
    return _row(saved) or {}


def list_mastery(owner: str, song_id: str) -> list[dict[str, Any]]:
    if not owner or not song_id:
        return []
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM learn_mastery WHERE owner=? AND song_id=?",
            (owner, song_id),
        ).fetchall()
    return _rows(rows)


def apply_mastery(
    owner: str,
    song_id: str,
    kind: str,
    item_key: str,
    *,
    text: str = "",
    zh: str = "",
    ok: bool,
) -> dict[str, Any]:
    now = now_ms()
    key = str(item_key or "").strip()
    kind = str(kind or "").strip()
    if not owner or not song_id or not kind or not key:
        return {}
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM learn_mastery WHERE owner=? AND song_id=? AND kind=? AND item_key=?",
            (owner, song_id, kind, key),
        ).fetchone()
        prev = _row(row)
        correct = int(prev["correct"]) if prev else 0
        wrong = int(prev["wrong"]) if prev else 0
        streak = int(prev["streak"]) if prev else 0
        mastered = int(prev["mastered"]) if prev else 0
        if ok:
            correct += 1
            streak += 1
            if streak >= MASTERY_STREAK:
                mastered = 1
        else:
            wrong += 1
            streak = 0
        label = text or (prev.get("text") if prev else "") or key
        gloss = zh or (prev.get("zh") if prev else "") or ""
        if prev:
            execute(
                conn,
                "UPDATE learn_mastery SET text=?, zh=?, correct=?, wrong=?, streak=?, "
                "mastered=?, updated_at=? WHERE owner=? AND song_id=? AND kind=? AND item_key=?",
                (
                    label,
                    gloss,
                    correct,
                    wrong,
                    streak,
                    mastered,
                    now,
                    owner,
                    song_id,
                    kind,
                    key,
                ),
            )
        else:
            execute(
                conn,
                "INSERT INTO learn_mastery "
                "(owner, song_id, kind, item_key, text, zh, correct, wrong, streak, mastered, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    owner,
                    song_id,
                    kind,
                    key,
                    label,
                    gloss,
                    correct,
                    wrong,
                    streak,
                    mastered,
                    now,
                ),
            )
        saved = execute(
            conn,
            "SELECT * FROM learn_mastery WHERE owner=? AND song_id=? AND kind=? AND item_key=?",
            (owner, song_id, kind, key),
        ).fetchone()
    return _row(saved) or {}


def list_mistakes(
    owner: str, song_id: str, *, open_only: bool = True
) -> list[dict[str, Any]]:
    if not owner or not song_id:
        return []
    sql = "SELECT * FROM learn_mistakes WHERE owner=? AND song_id=?"
    params: list[Any] = [owner, song_id]
    if open_only:
        sql += " AND resolved_at=0"
    sql += " ORDER BY last_wrong_at DESC, wrong_count DESC"
    with connect() as conn:
        rows = execute(conn, sql, params).fetchall()
    out = []
    for row in _rows(rows):
        payload = row.get("payload") or ""
        if isinstance(payload, str) and payload.startswith("{"):
            try:
                row["item"] = json.loads(payload)
            except json.JSONDecodeError:
                row["item"] = {}
        else:
            row["item"] = {}
        out.append(row)
    return out


def record_mistake(
    owner: str,
    song_id: str,
    *,
    qkind: str,
    item_key: str,
    prompt: str = "",
    stem: str = "",
    answer_text: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now_ms()
    key = str(item_key or "").strip()
    qkind = str(qkind or "").strip()
    if not owner or not song_id or not qkind or not key:
        return {}
    blob = json.dumps(payload or {}, ensure_ascii=False)
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (owner, song_id, qkind, key),
        ).fetchone()
        prev = _row(row)
        wrong_count = int(prev["wrong_count"]) + 1 if prev else 1
        if prev:
            # A repeat miss is a lapse: drop the box and make the card due now
            # so the mistake deck surfaces it in the very next session.
            plan = srs.schedule(int(prev.get("stage") or 0), False, now)
            execute(
                conn,
                "UPDATE learn_mistakes SET prompt=?, stem=?, answer_text=?, payload=?, "
                "wrong_count=?, correct_streak=0, last_wrong_at=?, resolved_at=0, "
                "stage=?, lapses=?, due_at=? "
                "WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
                (
                    prompt or prev.get("prompt") or "",
                    stem or prev.get("stem") or "",
                    answer_text or prev.get("answer_text") or "",
                    blob or prev.get("payload") or "",
                    wrong_count,
                    now,
                    plan["stage"],
                    int(prev.get("lapses") or 0) + 1,
                    now,
                    owner,
                    song_id,
                    qkind,
                    key,
                ),
            )
        else:
            execute(
                conn,
                "INSERT INTO learn_mistakes "
                "(owner, song_id, qkind, item_key, prompt, stem, answer_text, payload, "
                "wrong_count, correct_streak, last_wrong_at, resolved_at, "
                "stage, reps, lapses, due_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,?)",
                (
                    owner,
                    song_id,
                    qkind,
                    key,
                    prompt,
                    stem,
                    answer_text,
                    blob,
                    wrong_count,
                    0,
                    now,
                    now,
                ),
            )
        saved = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (owner, song_id, qkind, key),
        ).fetchone()
    return _row(saved) or {}


def note_correct(
    owner: str, song_id: str, qkind: str, item_key: str
) -> dict[str, Any] | None:
    key = str(item_key or "").strip()
    qkind = str(qkind or "").strip()
    if not owner or not song_id or not qkind or not key:
        return None
    now = now_ms()
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (owner, song_id, qkind, key),
        ).fetchone()
        prev = _row(row)
        if not prev:
            return None
        streak = int(prev["correct_streak"]) + 1
        resolved = now if streak >= MASTERY_STREAK else 0
        execute(
            conn,
            "UPDATE learn_mistakes SET correct_streak=?, resolved_at=? "
            "WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (streak, resolved, owner, song_id, qkind, key),
        )
        saved = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (owner, song_id, qkind, key),
        ).fetchone()
    return _row(saved)


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") or ""
    if isinstance(payload, str) and payload.startswith("{"):
        try:
            row["item"] = json.loads(payload)
        except json.JSONDecodeError:
            row["item"] = {}
    else:
        row["item"] = {}
    return row


def count_open_mistakes(owner: str) -> int:
    """Open mistakes across every song — the mistake deck's total."""
    if not owner:
        return 0
    with connect() as conn:
        row = execute(
            conn,
            "SELECT COUNT(*) AS n FROM learn_mistakes WHERE owner=? AND resolved_at=0",
            (owner,),
        ).fetchone()
    return int(dict(row).get("n") or 0) if row else 0


def list_open_mistakes(owner: str, limit: int = 500) -> list[dict[str, Any]]:
    if not owner:
        return []
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND resolved_at=0 "
            "ORDER BY last_wrong_at DESC LIMIT ?",
            (owner, max(1, min(2000, int(limit or 500)))),
        ).fetchall()
    return [_decode(row) for row in _rows(rows)]


def list_due_mistakes(
    owner: str, limit: int, now: int | None = None
) -> list[dict[str, Any]]:
    """Mistakes due today, across songs. Drives the mistake deck's session."""
    if not owner:
        return []
    cutoff = srs.end_of_day(now)
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND resolved_at=0 AND due_at<=? "
            "ORDER BY due_at, last_wrong_at DESC LIMIT ?",
            (owner, cutoff, max(1, int(limit or 10))),
        ).fetchall()
    return [_decode(row) for row in _rows(rows)]


def bump_mistake(
    owner: str,
    song_id: str,
    qkind: str,
    item_key: str,
    ok: bool,
    now: int | None = None,
) -> dict[str, Any] | None:
    """Apply one deck answer's schedule. Clearing the last box resolves the row.

    Distinct from `note_correct()`, which the in-song review path uses with its
    own two-in-a-row rule; both write the same row, neither resets the other.
    """
    key = str(item_key or "").strip()
    qkind = str(qkind or "").strip()
    if not owner or not song_id or not qkind or not key:
        return None
    moment = int(now if now is not None else now_ms())
    with _LOCK, connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (owner, song_id, qkind, key),
        ).fetchone()
        prev = _row(row)
        if not prev:
            return None
        plan = srs.schedule(int(prev.get("stage") or 0), bool(ok), moment)
        # Retiring the card and closing the notebook entry are the same event:
        # the song's campaign should stop counting it as an open mistake too.
        resolved = plan["retired_at"] or int(prev.get("resolved_at") or 0)
        execute(
            conn,
            "UPDATE learn_mistakes SET stage=?, reps=?, lapses=?, due_at=?, "
            "correct_streak=?, resolved_at=? "
            "WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (
                plan["stage"],
                int(prev.get("reps") or 0) + 1,
                int(prev.get("lapses") or 0) + (0 if ok else 1),
                plan["due_at"],
                int(prev.get("correct_streak") or 0) + 1 if ok else 0,
                resolved,
                owner,
                song_id,
                qkind,
                key,
            ),
        )
        saved = execute(
            conn,
            "SELECT * FROM learn_mistakes WHERE owner=? AND song_id=? AND qkind=? AND item_key=?",
            (owner, song_id, qkind, key),
        ).fetchone()
    return _row(saved)
