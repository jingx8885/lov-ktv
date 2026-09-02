"""Turn a deck's due rows into one round of Baicizhan-style cards.

Two decks share this module: `word` reads `learn_cards`, `mistake` replays the
question payload stored in `learn_mistakes`. Both come out as the same card
shape so the phone renders one UI.
"""

from __future__ import annotations

from typing import Any

from lovktv.locale.i18n import translate
from lovktv.workers import srs
from lovktv.workers.campaign import item_from_mistake
from lovktv.workers.learn import _choices, _question, _seeded_rng, _unique

RECITE_SCHEMA = "lovktv-recite-v1"
SESSION_SIZES = (10, 20, 30)
DEFAULT_SIZE = 10

# Climbing the boxes should get harder: recognition, then recall, then
# listening, then the word back in its line. Index by stage.
STAGE_KIND = ("meaning", "meaning", "reverse", "listen", "blank", "blank", "blank")


def clamp_size(size: Any) -> int:
    try:
        value = int(size)
    except (TypeError, ValueError):
        return DEFAULT_SIZE
    return min(SESSION_SIZES[-1], max(SESSION_SIZES[0], value))


def _gap(line: str, word: str) -> dict[str, str] | None:
    """Split the source line around its target word, for the cloze card."""
    if not line or not word or word not in line:
        return None
    before, after = line.split(word, 1)
    return {"before": before, "gap": word, "after": after}


def _kinds(card: dict[str, Any]) -> list[str]:
    """Question kinds this card can actually carry, easiest first.

    A collected word may have no gloss, no timing, or no source line; rather
    than shipping a broken card the deck falls back to whatever it does have.
    """
    zh = str(card.get("zh") or "").strip()
    text = str(card.get("text") or "").strip()
    line = str(card.get("line_text") or "").strip()
    has_audio = bool(card.get("song_id")) and int(card.get("end_ms") or 0) > int(
        card.get("start_ms") or 0
    )
    kinds = []
    if zh:
        kinds.append("meaning")
        kinds.append("reverse")
    if has_audio:
        kinds.append("listen")
    if _gap(line, text):
        kinds.append("blank")
    return kinds or ["meaning"]


def _detail(card: dict[str, Any]) -> dict[str, Any]:
    """The memory anchor shown after a miss: the word plus where it was sung."""
    return {
        "text": str(card.get("text") or ""),
        "zh": str(card.get("zh") or ""),
        "romaji": str(card.get("romaji") or ""),
        "line_text": str(card.get("line_text") or ""),
        "song_id": str(card.get("song_id") or ""),
        "song_title": str(card.get("song_title") or ""),
        "start_ms": int(card.get("start_ms") or 0),
        "end_ms": int(card.get("end_ms") or 0),
    }


def _word_card(
    card: dict[str, Any], pools: dict[str, list[str]], lang: str
) -> dict[str, Any] | None:
    text = str(card.get("text") or "").strip()
    if not text:
        return None
    cid = str(card.get("card_id") or "")
    stage = srs.clamp_stage(card.get("stage"))
    kinds = _kinds(card)
    want = STAGE_KIND[min(stage, len(STAGE_KIND) - 1)]
    kind = want if want in kinds else kinds[-1]
    rng = _seeded_rng("recite", cid, stage)
    detail = _detail(card)
    if kind == "reverse":
        item = _question(
            cid,
            "reverse",
            translate(lang, "api.recite_reverse"),
            str(card.get("zh") or ""),
            _choices(text, pools["text"], rng),
        )
    elif kind == "listen":
        item = _question(
            cid,
            "listen",
            translate(lang, "api.recite_listen"),
            "",
            _choices(text, pools["text"], rng),
        )
    elif kind == "blank":
        gap = _gap(detail["line_text"], text) or {}
        item = _question(
            cid,
            "blank",
            translate(lang, "api.recite_blank"),
            f"{gap.get('before', '')}____{gap.get('after', '')}",
            _choices(text, pools["text"], rng),
        )
        item["blank"] = gap
    else:
        item = _question(
            cid,
            "meaning",
            translate(lang, "api.recite_meaning", word=text),
            text,
            _choices(str(card.get("zh") or text), pools["zh"], rng),
        )
    item["card_id"] = cid
    item["ref"] = {"card_id": cid}
    item["stage"] = stage
    item["detail"] = detail
    # The listening card must not print the word it is asking for.
    item["audio"] = kind == "listen"
    return item


def mistake_ref(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("song_id") or ""),
            str(row.get("qkind") or ""),
            str(row.get("item_key") or ""),
        ]
    )


def parse_mistake_ref(ref: str) -> tuple[str, str, str]:
    """Inverse of `mistake_ref`. Song ids and kinds never contain `|`."""
    parts = str(ref or "").split("|", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0], parts[1], parts[2]


def _mistake_card(row: dict[str, Any], lang: str) -> dict[str, Any] | None:
    item = item_from_mistake(row)
    ref = mistake_ref(row)
    knowledge = (item or {}).get("knowledge") or {}
    text = str(knowledge.get("text") or row.get("stem") or row.get("item_key") or "")
    detail = {
        "text": text,
        "zh": str(knowledge.get("zh") or row.get("answer_text") or ""),
        "romaji": "",
        "line_text": str(row.get("stem") or ""),
        "song_id": str(row.get("song_id") or ""),
        "song_title": "",
        "start_ms": 0,
        "end_ms": 0,
    }
    if not item or not item.get("choices"):
        # Payloads from older rows (or match items, which need a different UI)
        # degrade to a plain "what did this mean" card.
        answer = detail["zh"] or text
        if not answer or not text:
            return None
        rng = _seeded_rng("recite", ref)
        item = _question(
            ref,
            "meaning",
            translate(lang, "api.recite_meaning", word=text),
            text,
            _choices(answer, [], rng),
        )
    else:
        item = dict(item)
        item["id"] = ref
    item["card_id"] = ref
    item["ref"] = {
        "song_id": str(row.get("song_id") or ""),
        "qkind": str(row.get("qkind") or ""),
        "item_key": str(row.get("item_key") or ""),
    }
    item["stage"] = srs.clamp_stage(row.get("stage"))
    item["detail"] = detail
    item["audio"] = False
    return item


def build_recite_session(
    deck: str,
    rows: list[dict[str, Any]],
    pool: list[dict[str, Any]] | None = None,
    lang: str = "zh",
) -> dict[str, Any]:
    """One round of cards. `pool` supplies distractors beyond the due rows."""
    cards: list[dict[str, Any]] = []
    if deck == "mistake":
        for row in rows:
            card = _mistake_card(row, lang)
            if card:
                cards.append(card)
    else:
        source = list(pool or []) or list(rows)
        pools = {
            "zh": _unique([str(row.get("zh") or "") for row in source]),
            "text": _unique([str(row.get("text") or "") for row in source]),
        }
        for row in rows:
            card = _word_card(row, pools, lang)
            if card:
                cards.append(card)
    return {
        "schema": RECITE_SCHEMA,
        "deck": deck if deck in ("word", "mistake") else "word",
        "cards": cards,
        "total": len(cards),
    }


def card_state(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "due_at": int(row.get("due_at") or 0),
        "reps": int(row.get("reps") or 0),
        "retired": int(row.get("retired_at") or 0) > 0,
    }


def mistake_state(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "due_at": int(row.get("due_at") or 0),
        "reps": int(row.get("reps") or 0),
        "retired": int(row.get("resolved_at") or 0) > 0,
    }


def deck_summary(
    deck: str,
    states: list[dict[str, Any]],
    day_info: dict[str, Any] | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    cutoff = srs.end_of_day(now)
    live = [state for state in states if not state["retired"]]
    info = day_info or {}
    return {
        "deck": deck if deck in ("word", "mistake") else "word",
        "total": len(states),
        "due": sum(1 for state in live if state["due_at"] <= cutoff),
        "new": sum(1 for state in live if not state["reps"]),
        "learning": sum(1 for state in live if state["reps"]),
        "mastered": sum(1 for state in states if state["retired"]),
        "streak": int(info.get("streak") or 0),
        "today": int(info.get("today") or 0),
        "day": str(info.get("day") or srs.day_key(now)),
        "sizes": list(SESSION_SIZES),
    }
