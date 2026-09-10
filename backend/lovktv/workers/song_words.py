"""Extract one song's vocabulary list from its lyric timeline.

Pure functions. The word *selection* is deliberately not reimplemented here:
`knowledge_words()` already encodes which tokens are worth learning (content
words, filler and particles dropped, with a particles-only fallback for lines
that have nothing else), and the campaign's word skill draws from the same
well. This module's job is to attach the anchor each vocabulary card needs —
pronunciation, and the line and audio window where the word was first sung.
"""

from __future__ import annotations

from typing import Any

from lovktv.storage.words import word_id
from lovktv.workers.campaign import knowledge_words, singable_cues
from lovktv.workers.learn import _norm, cue_text


def _token_romaji(token: dict[str, Any]) -> str:
    pronunciation = token.get("pronunciation")
    return _norm(
        token.get("romaji")
        or (pronunciation.get("value") if isinstance(pronunciation, dict) else "")
    )


def _anchors(cues: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """First sung occurrence of each surface form, keyed by normalized text.

    First rather than last: the earliest line is the one the user hears soonest
    when they replay the snippet, and it is stable as the song's later verses
    repeat the word.
    """
    found: dict[str, dict[str, Any]] = {}
    for cue in cues:
        line = cue_text(cue)
        cue_start = int(cue.get("start_ms") or 0)
        cue_end = int(cue.get("end_ms") or 0)
        for token in cue.get("tokens") or []:
            if not isinstance(token, dict):
                continue
            key = _norm(token.get("surface") or token.get("text"))
            if not key or key in found:
                continue
            start = int(token.get("start_ms") or cue_start)
            end = int(token.get("end_ms") or cue_end)
            found[key] = {
                "romaji": _token_romaji(token),
                "line_text": line,
                "start_ms": start,
                "end_ms": max(end, start),
            }
    return found


def song_words(
    timeline: dict[str, Any], song: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """The deduped vocabulary of one song, in sung order."""
    cues = singable_cues(timeline, song)
    anchors = _anchors(cues)
    language = _norm((song or {}).get("language"))
    out: list[dict[str, Any]] = []
    for word in knowledge_words(cues):
        text = _norm(word.get("text"))
        wid = word_id(language, text)
        if not wid:
            continue
        anchor = anchors.get(text) or {}
        out.append(
            {
                "word_id": wid,
                "language": language,
                "norm": word.get("key") or "",
                "text": text,
                "zh": _norm(word.get("zh")),
                "romaji": str(anchor.get("romaji") or ""),
                "line_text": str(anchor.get("line_text") or ""),
                "start_ms": int(anchor.get("start_ms") or 0),
                "end_ms": int(anchor.get("end_ms") or 0),
            }
        )
    return out


def merge_state(
    words: list[dict[str, Any]], saved: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Overlay the user's global state onto the song's extracted list.

    A word already met in another song arrives with its box intact, which is the
    whole point of a global word table: the filter screen shows it as known
    rather than offering it as new.
    """
    state = {str(row.get("word_id")): row for row in saved or []}
    out = []
    for word in words:
        row = state.get(word["word_id"]) or {}
        out.append(
            {
                **word,
                "stage": int(row.get("stage") or 0),
                "reps": int(row.get("reps") or 0),
                "due_at": int(row.get("due_at") or 0),
                "mastered": int(row.get("retired_at") or 0) > 0,
                "skipped": int(row.get("skipped_at") or 0) > 0,
                "known": bool(row),
            }
        )
    return out


def words_summary(
    rows: list[dict[str, Any]], now: int | None = None
) -> dict[str, Any]:
    """Counts the filter screen and the review entry both need."""
    from lovktv.workers import srs

    cutoff = srs.end_of_day(now)
    live = [row for row in rows if not row["skipped"] and not row["mastered"]]
    return {
        "total": len(rows),
        "kept": len(live),
        "skipped": sum(1 for row in rows if row["skipped"]),
        "mastered": sum(1 for row in rows if row["mastered"]),
        "new": sum(1 for row in live if not row["reps"]),
        "due": sum(1 for row in live if int(row["due_at"] or 0) <= cutoff),
    }
