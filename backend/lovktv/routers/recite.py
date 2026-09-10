"""Recitation decks: vocabulary and the mistake notebook, spaced out.

Two decks, one engine. `word` reads `learn_words` — one row per word per user,
so a word's box is shared by every song that uses it; `mistake` reads the SRS
columns on `learn_mistakes` so the in-song review path keeps writing one row.

Passing `song_id` narrows the word deck to one song's vocabulary, which is how
"learn this song's words" reuses the same cards, scheduler and streak instead of
forking a parallel deck.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from starlette.requests import Request

from lovktv.identity.quota import learn_owner
from lovktv.locale.i18n import request_lang
from lovktv.storage import learn as learn_store
from lovktv.storage import recite as recite_store
from lovktv.storage import words as words_store
from lovktv.workers import recite as recite_worker
from lovktv.workers import srs
from lovktv.services.http import fail

router = APIRouter()

MAX_IMPORT = 400
LIST_LIMIT = 500
WORD_STATES = ("all", "active", "skipped", "mastered")


def _deck(value: Any) -> str:
    deck = str(value or "word").strip()
    return deck if deck in recite_store.DECKS else "word"


def _card_view(row: dict[str, Any]) -> dict[str, Any]:
    """The list row the deck home renders. Scheduling state included so the
    phone can badge a card as new / learning / mastered without a second call.

    `card_id` carries the word id. The name is kept because it is already the
    deck's opaque reference — the mistake deck packs a composite key into the
    same field — and the phone threads it through unchanged.
    """
    return {
        "card_id": str(row.get("card_id") or row.get("word_id") or ""),
        "song_id": str(row.get("song_id") or ""),
        "song_title": str(row.get("song_title") or ""),
        "text": str(row.get("text") or ""),
        "zh": str(row.get("zh") or ""),
        "romaji": str(row.get("romaji") or ""),
        "line_text": str(row.get("line_text") or ""),
        "start_ms": int(row.get("start_ms") or 0),
        "end_ms": int(row.get("end_ms") or 0),
        "stage": srs.clamp_stage(row.get("stage")),
        "reps": int(row.get("reps") or 0),
        "due_at": int(row.get("due_at") or 0),
        "retired": int(row.get("retired_at") or 0) > 0,
        "skipped": int(row.get("skipped_at") or 0) > 0,
    }


def _mistake_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_id": recite_worker.mistake_ref(row),
        "song_id": str(row.get("song_id") or ""),
        "song_title": "",
        "text": str(row.get("stem") or row.get("item_key") or ""),
        "zh": str(row.get("answer_text") or ""),
        "romaji": "",
        "line_text": str(row.get("stem") or ""),
        "start_ms": 0,
        "end_ms": 0,
        "stage": srs.clamp_stage(row.get("stage")),
        "reps": int(row.get("reps") or 0),
        "due_at": int(row.get("due_at") or 0),
        "retired": int(row.get("resolved_at") or 0) > 0,
        "wrong_count": int(row.get("wrong_count") or 0),
    }


def _word_state(row: dict[str, Any]) -> dict[str, Any]:
    """Skipped words are out of the queue but stay in the totals, so the deck can
    say "12 set aside" and offer them back."""
    return {
        "due_at": int(row.get("due_at") or 0),
        "reps": int(row.get("reps") or 0),
        "retired": int(row.get("retired_at") or 0) > 0,
        "skipped": int(row.get("skipped_at") or 0) > 0,
    }


def _deck_payload(
    owner: str, deck: str, *, with_cards: bool = True, song_id: str = ""
) -> dict[str, Any]:
    day_info = recite_store.deck_streak(owner, deck)
    if deck == "mistake":
        rows = learn_store.list_open_mistakes(owner, limit=LIST_LIMIT)
        states = [recite_worker.mistake_state(row) for row in rows]
        cards = [_mistake_view(row) for row in rows] if with_cards else []
        summary = recite_worker.deck_summary(deck, states, day_info)
        return {**summary, "song_id": "", "cards": cards}
    rows = words_store.list_words(owner, song_id, limit=LIST_LIMIT)
    states = [_word_state(row) for row in rows]
    cards = [_card_view(row) for row in rows] if with_cards else []
    summary = recite_worker.deck_summary(deck, states, day_info)
    return {**summary, "song_id": song_id, "cards": cards}


@router.get("/api/learn/deck")
def api_recite_deck(
    request: Request, deck: str = "word", cards: int = 1, song_id: str = ""
) -> dict:
    """`cards=0` returns counts only — the campaign header just wants a total.
    `song_id` narrows the word deck to one song."""
    owner = learn_owner(request)
    name = _deck(deck)
    if name == "word":
        words_store.migrate_cards(owner)
    return _deck_payload(
        owner,
        name,
        with_cards=bool(cards),
        song_id=str(song_id or "").strip() if name == "word" else "",
    )


@router.post("/api/learn/cards")
def api_recite_card_add(request: Request, body: dict = Body(default_factory=dict)) -> dict:
    """Collect one word from the lyrics page. Idempotent by word id, so tapping
    the same word twice never resets the box already earned on it."""
    owner = learn_owner(request)
    words_store.migrate_cards(owner)
    payload = dict(body if isinstance(body, dict) else {})
    if not payload.get("language"):
        song = payload.get("song_id")
        if song:
            from lovktv.storage.store import get_song

            row = get_song(str(song)) or {}
            payload["language"] = row.get("language") or ""
    saved = words_store.upsert_word(owner, payload)
    if not saved:
        fail(request, 400, "api.recite_card_rejected", limit=words_store.MAX_WORDS)
    return {"card": _card_view(saved), "total": words_store.count_words(owner)}


@router.post("/api/learn/cards/import")
def api_recite_card_import(
    request: Request, body: dict = Body(default_factory=dict)
) -> dict:
    """Migrate the browser's localStorage word list. Idempotent by word id, so
    the phone may call it on every visit without forking duplicates."""
    owner = learn_owner(request)
    words_store.migrate_cards(owner)
    raw = body.get("cards") if isinstance(body, dict) else None
    if not isinstance(raw, list):
        fail(request, 400, "api.recite_bad_import")
    before = words_store.count_words(owner)
    seen = 0
    for card in raw[:MAX_IMPORT]:
        if not isinstance(card, dict):
            continue
        seen += 1
        words_store.upsert_word(owner, card)
    total = words_store.count_words(owner)
    return {
        "seen": seen,
        "added": max(0, total - before),
        "total": total,
        "deck": _deck_payload(owner, "word"),
    }


@router.delete("/api/learn/cards/{card_id}")
def api_recite_card_drop(request: Request, card_id: str) -> dict:
    """Set a word aside. A persistent flag, not a delete: the word keeps its
    history and can be restored, and the choice holds across every song."""
    owner = learn_owner(request)
    dropped = words_store.set_skipped(owner, [str(card_id or "").strip()], True)
    if not dropped:
        fail(request, 404, "api.recite_card_missing")
    return {"ok": True, "total": words_store.count_words(owner)}


@router.get("/api/learn/words")
def api_words_list(request: Request, state: str = "all", song_id: str = "") -> dict:
    """Global word management: review what was set aside or already mastered."""
    owner = learn_owner(request)
    words_store.migrate_cards(owner)
    want = state if state in WORD_STATES else "all"
    rows = words_store.list_words(
        owner, str(song_id or "").strip(), limit=words_store.MAX_WORDS
    )
    views = [_card_view(row) for row in rows]
    if want == "skipped":
        views = [row for row in views if row["skipped"]]
    elif want == "mastered":
        views = [row for row in views if row["retired"] and not row["skipped"]]
    elif want == "active":
        views = [row for row in views if not row["skipped"] and not row["retired"]]
    return {
        "state": want,
        "song_id": str(song_id or "").strip(),
        "total": len(rows),
        "skipped": sum(1 for row in views if row["skipped"]),
        "words": views,
    }


@router.post("/api/learn/words/restore")
def api_words_restore(request: Request, body: dict = Body(default_factory=dict)) -> dict:
    """Put a set-aside or mastered word back into the queue."""
    owner = learn_owner(request)
    wid = str((body if isinstance(body, dict) else {}).get("word_id") or "").strip()
    saved = words_store.restore_word(owner, wid)
    if not saved:
        fail(request, 404, "api.recite_card_missing")
    return {"word": _card_view(saved), "deck": _deck_payload(owner, "word")}


@router.get("/api/learn/session")
def api_recite_session(
    request: Request, deck: str = "word", size: int = 0, song_id: str = ""
) -> dict:
    owner = learn_owner(request)
    name = _deck(deck)
    limit = recite_worker.clamp_size(size or recite_worker.DEFAULT_SIZE)
    lang = request_lang(request)
    scope = str(song_id or "").strip() if name == "word" else ""
    if name == "mistake":
        rows = learn_store.list_due_mistakes(owner, limit)
        session = recite_worker.build_recite_session(name, rows, lang=lang)
    else:
        words_store.migrate_cards(owner)
        rows = words_store.due_words(owner, scope, limit)
        # Distractors come from the same scope as the questions, so a song-scoped
        # round never offers a choice from a song the user has not opened.
        pool = words_store.list_words(owner, scope, limit=LIST_LIMIT)
        session = recite_worker.build_recite_session(name, rows, pool=pool, lang=lang)
    if not session["cards"]:
        fail(request, 409, "api.recite_nothing_due")
    return {**session, "size": limit, "song_id": scope}


@router.post("/api/learn/session")
def api_recite_session_submit(
    request: Request, body: dict = Body(default_factory=dict)
) -> dict:
    """Apply one round's answers. `answers` carries the first verdict per card:
    a card the user re-drilled until correct still counts as a miss, which is
    what keeps a shaky word coming back tomorrow instead of in sixteen days."""
    owner = learn_owner(request)
    name = _deck(body.get("deck"))
    raw = body.get("answers")
    if not isinstance(raw, list):
        fail(request, 400, "api.recite_bad_submission")
    scope = str(body.get("song_id") or "").strip() if name == "word" else ""
    # A song-scoped submission may only grade words that song actually owns.
    allowed = words_store.song_word_ids(owner, scope) if scope else None
    seen: set[str] = set()
    graded = 0
    right = 0
    for entry in raw[: recite_worker.SESSION_SIZES[-1]]:
        if not isinstance(entry, dict):
            continue
        ref = str(entry.get("card_id") or "").strip()
        if not ref or ref in seen:
            continue
        ok = bool(entry.get("ok"))
        if name == "mistake":
            song_id, qkind, item_key = recite_worker.parse_mistake_ref(ref)
            saved = learn_store.bump_mistake(owner, song_id, qkind, item_key, ok)
        else:
            if allowed is not None and ref not in allowed:
                fail(request, 400, "api.recite_bad_submission")
            saved = words_store.bump_word(owner, ref, ok)
        if not saved:
            continue
        seen.add(ref)
        graded += 1
        right += 1 if ok else 0
    if graded:
        # One streak per deck: studying a single song still counts as the day's
        # vocabulary practice rather than opening a parallel check-in.
        recite_store.mark_day(owner, name, graded)
    return {
        "graded": graded,
        "correct": right,
        "pct": round(right * 100 / graded) if graded else 0,
        "deck": _deck_payload(owner, name, song_id=scope),
    }
