"""Recitation decks: collected words and the mistake notebook, spaced out.

Two decks, one engine. `word` reads `learn_cards`; `mistake` reads the SRS
columns on `learn_mistakes` so the in-song review path keeps writing one row.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from starlette.requests import Request

from lovktv.identity.quota import learn_owner
from lovktv.locale.i18n import request_lang
from lovktv.storage import learn as learn_store
from lovktv.storage import recite as recite_store
from lovktv.workers import recite as recite_worker
from lovktv.workers import srs
from lovktv.services.http import fail

router = APIRouter()

MAX_IMPORT = 400
LIST_LIMIT = 500


def _deck(value: Any) -> str:
    deck = str(value or "word").strip()
    return deck if deck in recite_store.DECKS else "word"


def _card_view(row: dict[str, Any]) -> dict[str, Any]:
    """The list row the deck home renders. Scheduling state included so the
    phone can badge a card as new / learning / mastered without a second call."""
    return {
        "card_id": str(row.get("card_id") or ""),
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


def _deck_payload(owner: str, deck: str, *, with_cards: bool = True) -> dict[str, Any]:
    day_info = recite_store.deck_streak(owner, deck)
    if deck == "mistake":
        rows = learn_store.list_open_mistakes(owner, limit=LIST_LIMIT)
        states = [recite_worker.mistake_state(row) for row in rows]
        cards = [_mistake_view(row) for row in rows] if with_cards else []
    else:
        rows = recite_store.list_cards(owner, limit=LIST_LIMIT)
        states = [recite_worker.card_state(row) for row in rows]
        cards = [_card_view(row) for row in rows] if with_cards else []
    summary = recite_worker.deck_summary(deck, states, day_info)
    return {**summary, "cards": cards}


@router.get("/api/learn/deck")
def api_recite_deck(request: Request, deck: str = "word", cards: int = 1) -> dict:
    """`cards=0` returns counts only — the campaign header just wants a total."""
    return _deck_payload(learn_owner(request), _deck(deck), with_cards=bool(cards))


@router.post("/api/learn/cards")
def api_recite_card_add(request: Request, body: dict = Body(default_factory=dict)) -> dict:
    owner = learn_owner(request)
    saved = recite_store.upsert_card(owner, body if isinstance(body, dict) else {})
    if not saved:
        fail(request, 400, "api.recite_card_rejected", limit=recite_store.MAX_CARDS)
    return {"card": _card_view(saved), "total": recite_store.count_cards(owner)}


@router.post("/api/learn/cards/import")
def api_recite_card_import(
    request: Request, body: dict = Body(default_factory=dict)
) -> dict:
    """Migrate the browser's localStorage word list. Idempotent by card_id, so
    the phone may call it on every visit without forking duplicates."""
    owner = learn_owner(request)
    raw = body.get("cards") if isinstance(body, dict) else None
    if not isinstance(raw, list):
        fail(request, 400, "api.recite_bad_import")
    result = recite_store.import_cards(owner, raw[:MAX_IMPORT])
    return {**result, "deck": _deck_payload(owner, "word")}


@router.delete("/api/learn/cards/{card_id}")
def api_recite_card_delete(request: Request, card_id: str) -> dict:
    owner = learn_owner(request)
    removed = recite_store.delete_card(owner, str(card_id or "").strip())
    if not removed:
        fail(request, 404, "api.recite_card_missing")
    return {"ok": True, "total": recite_store.count_cards(owner)}


@router.get("/api/learn/session")
def api_recite_session(request: Request, deck: str = "word", size: int = 0) -> dict:
    owner = learn_owner(request)
    name = _deck(deck)
    limit = recite_worker.clamp_size(size or recite_worker.DEFAULT_SIZE)
    lang = request_lang(request)
    if name == "mistake":
        rows = learn_store.list_due_mistakes(owner, limit)
        session = recite_worker.build_recite_session(name, rows, lang=lang)
    else:
        rows = recite_store.due_cards(owner, limit)
        pool = recite_store.list_cards(owner, limit=LIST_LIMIT)
        session = recite_worker.build_recite_session(name, rows, pool=pool, lang=lang)
    if not session["cards"]:
        fail(request, 409, "api.recite_nothing_due")
    return {**session, "size": limit}


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
            saved = recite_store.bump_card(owner, ref, ok)
        if not saved:
            continue
        seen.add(ref)
        graded += 1
        right += 1 if ok else 0
    if graded:
        recite_store.mark_day(owner, name, graded)
    return {
        "graded": graded,
        "correct": right,
        "pct": round(right * 100 / graded) if graded else 0,
        "deck": _deck_payload(owner, name),
    }
