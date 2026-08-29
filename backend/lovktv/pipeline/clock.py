"""Official LRC clock alignment with ASR/onset consensus."""

from __future__ import annotations

from typing import Any

from lovktv.pipeline.audio import vocal_regions
from lovktv.pipeline.bounds import _voice_covers, hold_lines_until_next
from lovktv.pipeline.constants import *
from lovktv.pipeline.energy import (
    _vocal_end_near,
    consensus_line_start,
    snap_holes_to_voice,
)
from lovktv.pipeline.lyrics import drop_credit_lines
from lovktv.pipeline.matching import (
    _best_asr_window,
    _usable_asr_words,
    accept_score,
    estimate_lrc_offset,
    normalize_lyric,
    vocal_phrases,
)


def align_lines_official_clock(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]] | None,
    language: str,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Place lines on official LRC, then vote with Whisper and vocal onsets."""
    lines = [
        item
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    if not lines:
        return []
    asr_words = _usable_asr_words(asr_words or [])
    texts = [str(item.get("text") or "") for item in asr_words]
    accept = accept_score(language)
    regions = vocal_regions(envelope or [], hop_ms) if envelope else []
    phrases = vocal_phrases(regions) if regions else []
    timed = [item for item in lines if item.get("ms") is not None]
    shift = 0
    if timed and phrases:
        first_ms = int(timed[0]["ms"])
        later_alive = any(
            _voice_covers(regions, int(item["ms"]))
            for item in timed[1:]
            if item.get("ms") is not None
        )
        if (
            first_ms < 1000 or not _voice_covers(regions, first_ms)
        ) and not later_alive:
            shift = estimate_lrc_offset(timed, phrases)

    cursor = 0
    bounds: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        raw = str(line.get("text") or "")
        known = normalize_lyric(raw, language)
        official = int(line["ms"]) + shift if line.get("ms") is not None else None
        next_official = (
            int(lines[index + 1]["ms"]) + shift
            if index + 1 < len(lines) and lines[index + 1].get("ms") is not None
            else None
        )
        start_ms = (
            official
            if official is not None
            else (int(bounds[-1]["end_ms"]) if bounds else 0)
        )
        from_asr = False
        asr_start = None
        match = None
        if asr_words and known and official is not None:
            earliest = official - ASR_WINDOW_BEFORE
            latest = official + ASR_RESCUE_AFTER
            if next_official is not None:
                latest = min(latest, next_official + 1500)
            else:
                latest = official + MAX_LINE_MS + 2500
            if bounds:
                earliest = max(earliest, int(bounds[-1]["end_ms"]))
            match = _best_asr_window(
                known, asr_words, texts, language, cursor, earliest, latest, accept
            )
            if match:
                asr_start = int(asr_words[match[1]]["start_ms"])
                cursor = match[2]
        if official is not None:
            start_ms, from_asr = consensus_line_start(
                official,
                asr_start,
                regions,
                next_official,
                int(bounds[-1]["end_ms"]) if bounds else 0,
            )
        if bounds:
            start_ms = max(start_ms, int(bounds[-1]["start_ms"]) + 80)
        if line.get("end_ms") is not None:
            end_ms = int(line["end_ms"]) + shift
        elif next_official is not None and next_official - start_ms <= MAX_LINE_MS:
            end_ms = next_official
        elif regions:
            end_ms = _vocal_end_near(start_ms, phrases or regions)
            if next_official is not None:
                end_ms = min(end_ms, next_official)
        else:
            known_n = (
                len(known.split()) if language == "en" else max(1, len(known or "x"))
            )
            end_ms = start_ms + max(MIN_LINE_MS, min(MAX_LINE_MS, 180 * known_n))
        if match and next_official is None:
            end_ms = max(end_ms, int(asr_words[match[2] - 1]["end_ms"]))
        bounds.append(
            {
                "text": raw,
                "start_ms": max(0, start_ms),
                "end_ms": max(start_ms + MIN_LINE_MS, end_ms),
                "from_asr": from_asr,
            }
        )
    snap_holes_to_voice(bounds, regions)
    for index, row in enumerate(bounds[:-1]):
        nxt = int(bounds[index + 1]["start_ms"])
        if row["end_ms"] > nxt:
            row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, nxt)
    return hold_lines_until_next(bounds)
