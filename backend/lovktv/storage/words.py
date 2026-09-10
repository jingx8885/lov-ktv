"""Global vocabulary state: one row per (owner, language, normalized word).

The deck used to key scheduling on `learn_cards.card_id`, which folds the song
id into the hash — so "なみだ" met in two songs was two unrelated cards with two
separate boxes. Here the id is the word alone, so proficiency and the "don't
make me learn this" flag follow the word across every song that uses it.

`learn_word_sources` records where a word was met. A song-scoped review joins
through it; the cross-song deck reads its most recent row to get the lyric line
and audio window a card needs for its cloze / listening / detail views.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

from lovktv.core.db import execute
from lovktv.storage.store import connect, now_ms
from lovktv.workers import srs
from lovktv.workers.learn import _norm

MAX_WORDS = 5000
MIGRATION_CARDS = "cards_to_words"
_LOCK = threading.Lock()

_WORD_FIELDS = ("language", "text", "zh", "romaji")
_SOURCE_FIELDS = ("song_id", "song_title", "line_text")


def _rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def normalize(text: Any) -> str:
    """The identity of a word. NFKC + strip (shared with question building) then
    casefold, so "Tears" and "tears" are one word rather than two."""
    return _norm(text).casefold()


def word_id(language: Any, text: Any) -> str:
    """Stable id, deliberately free of any song id — that is what lets the same
    word carry one box across songs."""
    norm = normalize(text)
    if not norm:
        return ""
    raw = f"{_norm(language).lower()}:{norm}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _clean(word: dict[str, Any]) -> dict[str, Any]:
    out = {name: _norm(word.get(name))[:400] for name in _WORD_FIELDS + _SOURCE_FIELDS}
    for name in ("start_ms", "end_ms"):
        try:
            out[name] = max(0, int(word.get(name) or 0))
        except (TypeError, ValueError):
            out[name] = 0
    out["norm"] = normalize(out["text"])
    out["word_id"] = word_id(out["language"], out["text"])
    return out


# ------------------------------------------------------------------- reading


def get_word(owner: str, wid: str) -> dict[str, Any]:
    if not owner or not wid:
        return {}
    with connect() as conn:
        row = execute(
            conn, "SELECT * FROM learn_words WHERE owner=? AND word_id=?", (owner, wid)
        ).fetchone()
    return dict(row) if row else {}


def get_words(owner: str, ids: list[str]) -> list[dict[str, Any]]:
    """Bulk read by word id, regardless of which song they came from.

    The filter screen needs this rather than a song-scoped list: a word this
    song shares with one the user already studied must show up as known, and it
    has no source row for *this* song until setup runs.
    """
    owner = str(owner or "").strip()
    wanted = [str(item or "").strip() for item in ids or []]
    wanted = [item for item in wanted if item]
    if not owner or not wanted:
        return []
    out: list[dict[str, Any]] = []
    with connect() as conn:
        # Chunked to stay clear of the parameter ceiling on long songs.
        for start in range(0, len(wanted), 200):
            chunk = wanted[start : start + 200]
            marks = ",".join("?" for _ in chunk)
            out.extend(
                _rows(
                    execute(
                        conn,
                        f"SELECT * FROM learn_words WHERE owner=? AND word_id IN ({marks})",
                        (owner, *chunk),
                    ).fetchall()
                )
            )
    return out


def _anchor_map(conn: Any, owner: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Newest source row per word. A word met in three songs shows the one it was
    most recently collected from, which is the context the user just saw."""
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = _rows(
        execute(
            conn,
            f"SELECT * FROM learn_word_sources WHERE owner=? AND word_id IN ({marks}) "
            "ORDER BY created_at",
            (owner, *ids),
        ).fetchall()
    )
    return {str(row.get("word_id")): row for row in rows}


def _decorate(conn: Any, owner: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge each word with its anchor so callers see the same shape the card
    views and session builder already consume."""
    anchors = _anchor_map(conn, owner, [str(row.get("word_id")) for row in rows])
    out = []
    for row in rows:
        anchor = anchors.get(str(row.get("word_id"))) or {}
        merged = dict(row)
        merged["card_id"] = str(row.get("word_id") or "")
        merged["song_id"] = str(anchor.get("song_id") or "")
        merged["song_title"] = str(anchor.get("song_title") or "")
        merged["line_text"] = str(anchor.get("line_text") or "")
        merged["start_ms"] = int(anchor.get("start_ms") or 0)
        merged["end_ms"] = int(anchor.get("end_ms") or 0)
        merged["skipped"] = int(row.get("skipped_at") or 0) > 0
        out.append(merged)
    return out


def _scope(song_id: str) -> tuple[str, list[Any]]:
    """Song-scoped queries reach through the source table; global ones don't."""
    if not song_id:
        return "", []
    return (
        " AND w.word_id IN (SELECT word_id FROM learn_word_sources "
        "WHERE owner=w.owner AND song_id=?)",
        [song_id],
    )


def list_words(
    owner: str,
    song_id: str = "",
    limit: int = 500,
    *,
    include_skipped: bool = True,
) -> list[dict[str, Any]]:
    if not owner:
        return []
    clause, params = _scope(str(song_id or "").strip())
    sql = f"SELECT w.* FROM learn_words w WHERE w.owner=?{clause}"
    if not include_skipped:
        sql += " AND w.skipped_at=0"
    sql += " ORDER BY w.created_at DESC LIMIT ?"
    with connect() as conn:
        rows = _rows(
            execute(
                conn,
                sql,
                (owner, *params, max(1, min(MAX_WORDS, int(limit or 500)))),
            ).fetchall()
        )
        return _decorate(conn, owner, rows)


def count_words(owner: str, song_id: str = "") -> int:
    if not owner:
        return 0
    clause, params = _scope(str(song_id or "").strip())
    with connect() as conn:
        row = execute(
            conn,
            f"SELECT COUNT(*) AS n FROM learn_words w WHERE w.owner=?{clause}",
            (owner, *params),
        ).fetchone()
    return int(dict(row).get("n") or 0) if row else 0


def due_words(
    owner: str, song_id: str = "", limit: int = 10, now: int | None = None
) -> list[dict[str, Any]]:
    """Words due today, oldest-due first. Skipped and mastered words never queue."""
    if not owner:
        return []
    cutoff = srs.end_of_day(now)
    clause, params = _scope(str(song_id or "").strip())
    with connect() as conn:
        rows = _rows(
            execute(
                conn,
                f"SELECT w.* FROM learn_words w WHERE w.owner=? AND w.skipped_at=0 "
                f"AND w.retired_at=0 AND w.due_at<=?{clause} "
                "ORDER BY w.due_at, w.created_at LIMIT ?",
                (owner, cutoff, *params, max(1, int(limit or 10))),
            ).fetchall()
        )
        return _decorate(conn, owner, rows)


def song_word_ids(owner: str, song_id: str) -> set[str]:
    """Which words this song owns — the guard against a forged answer crediting
    a word the user never saw here."""
    if not owner or not song_id:
        return set()
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT word_id FROM learn_word_sources WHERE owner=? AND song_id=?",
            (owner, song_id),
        ).fetchall()
    return {str(dict(row).get("word_id")) for row in rows}


def has_song_setup(owner: str, song_id: str) -> bool:
    """True once the user has confirmed a word list for this song. Drives whether
    the phone opens the filter screen or goes straight to review."""
    return bool(song_word_ids(owner, song_id))


# ------------------------------------------------------------------- writing


def _write_source(conn: Any, owner: str, body: dict[str, Any], now: int) -> None:
    if not body["song_id"]:
        return
    prev = execute(
        conn,
        "SELECT owner FROM learn_word_sources WHERE owner=? AND word_id=? AND song_id=?",
        (owner, body["word_id"], body["song_id"]),
    ).fetchone()
    if prev:
        execute(
            conn,
            "UPDATE learn_word_sources SET song_title=?, line_text=?, start_ms=?, end_ms=? "
            "WHERE owner=? AND word_id=? AND song_id=?",
            (
                body["song_title"],
                body["line_text"],
                body["start_ms"],
                body["end_ms"],
                owner,
                body["word_id"],
                body["song_id"],
            ),
        )
        return
    execute(
        conn,
        "INSERT INTO learn_word_sources (owner, word_id, song_id, song_title, line_text, "
        "start_ms, end_ms, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            owner,
            body["word_id"],
            body["song_id"],
            body["song_title"],
            body["line_text"],
            body["start_ms"],
            body["end_ms"],
            now,
        ),
    )


def _write_word(
    conn: Any, owner: str, body: dict[str, Any], now: int, *, skipped: bool | None = None
) -> bool:
    """Create the word, or refresh its wording. Scheduling state is never reset —
    re-meeting a word in another song must not cost the user their progress."""
    prev = execute(
        conn,
        "SELECT * FROM learn_words WHERE owner=? AND word_id=?",
        (owner, body["word_id"]),
    ).fetchone()
    if prev:
        row = dict(prev)
        mark = int(row.get("skipped_at") or 0)
        if skipped is True and not mark:
            mark = now
        elif skipped is False:
            mark = 0
        execute(
            conn,
            "UPDATE learn_words SET language=?, norm=?, text=?, zh=?, romaji=?, skipped_at=? "
            "WHERE owner=? AND word_id=?",
            (
                body["language"] or row.get("language") or "",
                body["norm"],
                body["text"] or row.get("text") or "",
                body["zh"] or row.get("zh") or "",
                body["romaji"] or row.get("romaji") or "",
                mark,
                owner,
                body["word_id"],
            ),
        )
        return True
    total = execute(
        conn, "SELECT COUNT(*) AS n FROM learn_words WHERE owner=?", (owner,)
    ).fetchone()
    if int(dict(total).get("n") or 0) >= MAX_WORDS:
        return False
    execute(
        conn,
        "INSERT INTO learn_words (owner, word_id, language, norm, text, zh, romaji, "
        "stage, reps, lapses, due_at, last_at, created_at, retired_at, skipped_at) "
        "VALUES (?,?,?,?,?,?,?,0,0,0,?,0,?,0,?)",
        (
            owner,
            body["word_id"],
            body["language"],
            body["norm"],
            body["text"],
            body["zh"],
            body["romaji"],
            now,
            now,
            now if skipped is True else 0,
        ),
    )
    return True


def upsert_word(owner: str, word: dict[str, Any]) -> dict[str, Any]:
    """Collect one word (the lyrics-page tap). Idempotent by word id."""
    owner = str(owner or "").strip()
    body = _clean(word if isinstance(word, dict) else {})
    if not owner or not body["word_id"]:
        return {}
    now = now_ms()
    with _LOCK, connect() as conn:
        if not _write_word(conn, owner, body, now):
            return {}
        _write_source(conn, owner, body, now)
        rows = _rows(
            execute(
                conn,
                "SELECT * FROM learn_words WHERE owner=? AND word_id=?",
                (owner, body["word_id"]),
            ).fetchall()
        )
        saved = _decorate(conn, owner, rows)
    return saved[0] if saved else {}


def setup_song(
    owner: str,
    song_id: str,
    keep: list[dict[str, Any]],
    skip: list[dict[str, Any]],
) -> dict[str, int]:
    """Save one song's confirmed word list.

    Idempotent by construction: both halves go through `_write_word`, which only
    ever refreshes wording and the skip flag. Re-submitting the same choice
    cannot add a rep or move a box, so a double-tapped confirm is harmless.
    """
    owner = str(owner or "").strip()
    song_id = str(song_id or "").strip()
    if not owner or not song_id:
        return {"kept": 0, "skipped": 0}
    now = now_ms()
    kept = 0
    dropped = 0
    with _LOCK, connect() as conn:
        for word, is_skip in [(item, False) for item in keep or []] + [
            (item, True) for item in skip or []
        ]:
            body = _clean(word if isinstance(word, dict) else {})
            body["song_id"] = song_id
            if not body["word_id"]:
                continue
            if not _write_word(conn, owner, body, now, skipped=is_skip):
                continue
            _write_source(conn, owner, body, now)
            if is_skip:
                dropped += 1
            else:
                kept += 1
    return {"kept": kept, "skipped": dropped}


def bump_word(
    owner: str, wid: str, ok: bool, now: int | None = None
) -> dict[str, Any]:
    """Apply one answer's schedule. Clearing the last box masters the word."""
    prev = get_word(owner, wid)
    if not prev:
        return {}
    moment = int(now if now is not None else now_ms())
    plan = srs.schedule(int(prev.get("stage") or 0), bool(ok), moment)
    with _LOCK, connect() as conn:
        execute(
            conn,
            "UPDATE learn_words SET stage=?, reps=?, lapses=?, due_at=?, last_at=?, "
            "retired_at=? WHERE owner=? AND word_id=?",
            (
                plan["stage"],
                int(prev.get("reps") or 0) + 1,
                int(prev.get("lapses") or 0) + (0 if ok else 1),
                plan["due_at"],
                moment,
                plan["retired_at"],
                owner,
                wid,
            ),
        )
    return get_word(owner, wid)


def set_skipped(owner: str, word_ids: list[str], skipped: bool) -> int:
    """Cut words from the queue, or put them back. A persistent flag rather than
    a delete, so the history and the box survive being set aside."""
    owner = str(owner or "").strip()
    ids = [str(item or "").strip() for item in word_ids or []]
    ids = [item for item in ids if item]
    if not owner or not ids:
        return 0
    mark = now_ms() if skipped else 0
    changed = 0
    with _LOCK, connect() as conn:
        for wid in ids:
            cur = execute(
                conn,
                "UPDATE learn_words SET skipped_at=? WHERE owner=? AND word_id=?",
                (mark, owner, wid),
            )
            changed += int(getattr(cur, "rowcount", 0) or 0)
    return changed


def restore_word(owner: str, wid: str) -> dict[str, Any]:
    """Bring a cut or mastered word back into rotation.

    Clearing `skipped_at` alone would leave a mastered word still retired and
    therefore still unqueued, so this also drops it one box and makes it due —
    the user asking for it back wants to see it, not to be told it is finished.
    """
    owner = str(owner or "").strip()
    prev = get_word(owner, wid)
    if not prev:
        return {}
    now = now_ms()
    stage = srs.clamp_stage(prev.get("stage"))
    retired = int(prev.get("retired_at") or 0) > 0
    if retired:
        stage = max(0, srs.MAX_STAGE - 1)
    with _LOCK, connect() as conn:
        execute(
            conn,
            "UPDATE learn_words SET skipped_at=0, retired_at=0, stage=?, due_at=? "
            "WHERE owner=? AND word_id=?",
            (stage, now, owner, wid),
        )
    return get_word(owner, wid)


# ----------------------------------------------------------------- migration


def _merge_card(target: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    """Fold a legacy card into a word record. Two cards for the same word (one
    per song) collapse to the better of the two: the furthest box, the most
    reps, and the soonest review — never a reset."""
    due = int(card.get("due_at") or 0)
    prev_due = int(target.get("due_at") or 0)
    target["stage"] = max(int(target.get("stage") or 0), int(card.get("stage") or 0))
    target["reps"] = max(int(target.get("reps") or 0), int(card.get("reps") or 0))
    target["lapses"] = max(int(target.get("lapses") or 0), int(card.get("lapses") or 0))
    target["retired_at"] = max(
        int(target.get("retired_at") or 0), int(card.get("retired_at") or 0)
    )
    target["due_at"] = min(prev_due, due) if prev_due and due else (prev_due or due)
    target["created_at"] = min(
        int(target.get("created_at") or 0) or int(card.get("created_at") or 0),
        int(card.get("created_at") or 0) or int(target.get("created_at") or 0),
    )
    for name in ("zh", "romaji"):
        if not target.get(name):
            target[name] = _norm(card.get(name))
    return target


def migrate_cards(owner: str) -> dict[str, int]:
    """Lazily fold `learn_cards` into `learn_words`, once per owner.

    The write itself is idempotent; the marker only saves re-reading the legacy
    table on every deck open. `text` is the word — `item_key` is a composite
    (`song:text:start_ms`) the browser minted and is not a word form.
    """
    owner = str(owner or "").strip()
    if not owner:
        return {"words": 0, "cards": 0, "migrated": False}
    with connect() as conn:
        done = execute(
            conn,
            "SELECT owner FROM learn_migrations WHERE owner=? AND kind=?",
            (owner, MIGRATION_CARDS),
        ).fetchone()
        if done:
            return {"words": 0, "cards": 0, "migrated": False}
        cards = _rows(
            execute(
                conn,
                "SELECT c.*, COALESCE(s.language, '') AS language FROM learn_cards c "
                "LEFT JOIN songs s ON s.id = c.song_id WHERE c.owner=?",
                (owner,),
            ).fetchall()
        )
    folded: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []
    for card in cards:
        body = _clean(
            {
                "language": card.get("language"),
                "text": card.get("text"),
                "zh": card.get("zh"),
                "romaji": card.get("romaji"),
                "song_id": card.get("song_id"),
                "song_title": card.get("song_title"),
                "line_text": card.get("line_text"),
                "start_ms": card.get("start_ms"),
                "end_ms": card.get("end_ms"),
            }
        )
        if not body["word_id"]:
            continue
        if body["song_id"]:
            sources.append(body)
        folded[body["word_id"]] = _merge_card(folded.get(body["word_id"]) or body, card)
    now = now_ms()
    with _LOCK, connect() as conn:
        for wid, body in folded.items():
            prev = execute(
                conn, "SELECT * FROM learn_words WHERE owner=? AND word_id=?", (owner, wid)
            ).fetchone()
            if prev:
                continue
            retired = int(body.get("retired_at") or 0)
            execute(
                conn,
                "INSERT INTO learn_words (owner, word_id, language, norm, text, zh, romaji, "
                "stage, reps, lapses, due_at, last_at, created_at, retired_at, skipped_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (
                    owner,
                    wid,
                    body["language"],
                    body["norm"],
                    body["text"],
                    body["zh"],
                    body["romaji"],
                    srs.clamp_stage(body.get("stage")),
                    int(body.get("reps") or 0),
                    int(body.get("lapses") or 0),
                    0 if retired else int(body.get("due_at") or now),
                    0,
                    int(body.get("created_at") or now),
                    retired,
                ),
            )
        for body in sources:
            _write_source(conn, owner, body, now)
        execute(
            conn,
            "INSERT INTO learn_migrations (owner, kind, created_at) VALUES (?,?,?)",
            (owner, MIGRATION_CARDS, now),
        )
    return {"words": len(folded), "cards": len(cards), "migrated": True}
