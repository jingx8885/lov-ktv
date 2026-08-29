"""ASR-anchored and duration-fallback line boundary helpers."""

from __future__ import annotations

from typing import Any

from lovktv.pipeline.audio import energy_token_spans, snap_to_onset, vocal_regions
from lovktv.pipeline.constants import *
from lovktv.pipeline.lyrics import drop_credit_lines
from lovktv.pipeline.matching import _best_asr_window, _usable_asr_words, accept_score, estimate_asr_offset, normalize_lyric

def _fallback_line_bounds(
    line: dict[str, Any],
    known_n: int,
    shift: int,
    prev_end: int,
) -> tuple[int, int]:
    if line.get("ms") is not None:
        start_ms = int(line["ms"]) + shift
    else:
        start_ms = prev_end
    if line.get("end_ms") is not None:
        end_ms = int(line["end_ms"]) + shift
    else:
        end_ms = start_ms + max(MIN_LINE_MS, min(MAX_LINE_MS, 180 * known_n))
    return start_ms, max(start_ms + MIN_LINE_MS, end_ms)

def _voice_covers(
    regions: list[tuple[int, int]],
    target_ms: int,
    slop_ms: int = 400,
) -> bool:
    return any(start - slop_ms <= target_ms <= end + slop_ms for start, end in regions)

def _append_bound(
    bounds: list[dict[str, Any]],
    text: str,
    start_ms: int,
    end_ms: int,
    from_asr: bool = False,
) -> None:
    if bounds:
        prev = bounds[-1]
        if start_ms < prev["end_ms"]:
            if prev.get("from_asr") and not from_asr:
                start_ms = int(prev["end_ms"])
            else:
                prev["end_ms"] = max(prev["start_ms"] + MIN_LINE_MS, start_ms)
                start_ms = max(start_ms, prev["end_ms"])
    start_ms = max(0, start_ms)
    end_ms = max(start_ms + MIN_LINE_MS, end_ms)
    bounds.append({"text": text, "start_ms": start_ms, "end_ms": end_ms, "from_asr": from_asr})

def align_lines_to_asr(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Walk ASR left-to-right so repeated chorus lines get later spans."""
    asr_words = _usable_asr_words(asr_words)
    if not asr_words:
        return []
    lines = drop_credit_lines(lines, language)
    cursor = 0
    bounds: list[dict[str, Any]] = []
    texts = [str(item.get("text") or "") for item in asr_words]
    accept = accept_score(language)
    shift = estimate_asr_offset(lines, asr_words, language)
    local_shift = shift
    regions = vocal_regions(envelope or [], hop_ms) if envelope else []
    for line in lines:
        raw_text = str(line.get("text") or "")
        known = normalize_lyric(raw_text, language)
        if not known:
            continue
        known_n = len(known.split()) if language == "en" else max(1, len(known))
        official_ms = int(line["ms"]) if line.get("ms") is not None else None
        expected_ms = official_ms + shift if official_ms is not None else None
        earliest = None if expected_ms is None else expected_ms - ASR_WINDOW_BEFORE
        latest = None if expected_ms is None else expected_ms + ASR_WINDOW_AFTER
        # After an ASR hit, later official stamps may have drifted by the same gap.
        if official_ms is not None and bounds and bounds[-1].get("from_asr"):
            drifted = official_ms + local_shift
            earliest = min(earliest or drifted, drifted - ASR_WINDOW_BEFORE)
            latest = max(latest or drifted, drifted + ASR_WINDOW_AFTER)
        match = _best_asr_window(
            known,
            asr_words,
            texts,
            language,
            cursor,
            earliest,
            latest,
            accept,
        )
        # First sung line, or a 0:00 title copy, may start earlier than the stamp.
        if not match and expected_ms is not None and (
            not bounds
            or (
                bounds[-1]["text"] == raw_text
                and int(bounds[-1]["start_ms"]) < 3000
            )
        ):
            match = _best_asr_window(
                known,
                asr_words,
                texts,
                language,
                cursor,
                0,
                expected_ms + ASR_WINDOW_AFTER,
                accept,
            )
        official_alive = official_ms is not None and _voice_covers(regions, official_ms)
        # Official LRC in a hole (wrong stamp / long instrumental): look further.
        # Skip 0:00 title rows so a later sung copy cannot pull the clock.
        if (
            not match
            and expected_ms is not None
            and official_ms is not None
            and official_ms >= 1000
            and not official_alive
        ):
            match = _best_asr_window(
                known,
                asr_words,
                texts,
                language,
                cursor,
                None if earliest is None else min(earliest, expected_ms - ASR_WINDOW_BEFORE),
                expected_ms + ASR_RESCUE_AFTER,
                accept,
            )
        asr_start = int(asr_words[match[1]]["start_ms"]) if match else None
        asr_in_hole = asr_start is not None and not _voice_covers(regions, asr_start)
        prefer_official = (
            match is not None
            and official_ms is not None
            and official_alive
            and asr_start is not None
            and (
                not bounds
                or official_ms + 200 >= int(bounds[-1]["end_ms"]) - 600
            )
            and (
                asr_start - official_ms > LATE_ASR_SLACK_MS
                or (official_ms - asr_start > EARLY_ASR_SLACK_MS and asr_in_hole)
            )
        )
        if match and not prefer_official:
            start_ms = int(asr_words[match[1]]["start_ms"])
            end_ms = int(asr_words[match[2] - 1]["end_ms"])
            cursor = match[2]
            local_shift = start_ms - official_ms if official_ms is not None else local_shift
        else:
            if match and prefer_official:
                cursor = match[2]
                local_shift = shift
            start_ms, end_ms = _fallback_line_bounds(
                line,
                known_n,
                0 if prefer_official else local_shift,
                bounds[-1]["end_ms"] if bounds else 0,
            )
            match = None
        _append_bound(bounds, raw_text, start_ms, end_ms, from_asr=bool(match))
    snap_unmatched_to_voice(bounds, regions)
    restore_short_official_gaps(bounds, lines, shift)
    if bounds and asr_words:
        last_asr = int(asr_words[-1]["end_ms"])
        last = bounds[-1]
        if last_asr > int(last["end_ms"]) and int(last["end_ms"]) - int(last["start_ms"]) < 2500:
            last["end_ms"] = min(last_asr, int(last["start_ms"]) + MAX_LINE_MS)
    return hold_lines_until_next(bounds)

def restore_short_official_gaps(
    bounds: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    shift: int,
) -> list[dict[str, Any]]:
    """Keep short chorus tags from being crushed below the official LRC gap."""
    official_times: dict[str, list[int]] = {}
    for line in lines:
        if line.get("ms") is None:
            continue
        official_times.setdefault(str(line.get("text") or ""), []).append(int(line["ms"]) + shift)
    used: dict[str, int] = {}
    for index, row in enumerate(bounds[:-1]):
        text = str(row.get("text") or "")
        nth = used.get(text, 0)
        used[text] = nth + 1
        times = official_times.get(text) or []
        if nth >= len(times):
            continue
        nxt = bounds[index + 1]
        nxt_text = str(nxt.get("text") or "")
        nxt_times = official_times.get(nxt_text) or []
        nxt_nth = used.get(nxt_text, 0)
        if nxt_nth >= len(nxt_times):
            continue
        official_gap = nxt_times[nxt_nth] - times[nth]
        if official_gap < 500 or int(row["end_ms"]) - int(row["start_ms"]) >= 800:
            continue
        new_end = min(nxt_times[nxt_nth], int(row["start_ms"]) + official_gap)
        if new_end <= int(row["end_ms"]):
            continue
        row["end_ms"] = new_end
        nxt["start_ms"] = max(int(nxt["start_ms"]), new_end)
        nxt["end_ms"] = max(int(nxt["end_ms"]), nxt["start_ms"] + MIN_LINE_MS)
    return bounds

def assign_plain_lines(
    texts: list[str],
    regions: list[tuple[int, int]],
    duration_ms: int,
) -> list[dict[str, Any]]:
    if not texts:
        return []
    slots = list(regions)
    if not slots:
        unit = max(duration_ms, len(texts) * 1000) / len(texts)
        return [{"ms": int(index * unit), "text": text, "end_ms": int((index + 1) * unit)} for index, text in enumerate(texts)]
    while len(slots) < len(texts):
        idx = max(range(len(slots)), key=lambda i: slots[i][1] - slots[i][0])
        start_ms, end_ms = slots[idx]
        mid = (start_ms + end_ms) // 2
        slots[idx : idx + 1] = [(start_ms, mid), (mid, end_ms)]
    while len(slots) > len(texts):
        start_ms, _ = slots[-2]
        _, end_ms = slots[-1]
        slots[-2:] = [(start_ms, end_ms)]
    return [
        {"ms": start_ms, "text": text, "end_ms": end_ms}
        for text, (start_ms, end_ms) in zip(texts, slots)
    ]

def line_sing_end(
    start_ms: int,
    display_end: int,
    regions: list[tuple[int, int]],
) -> int:
    """When the singer finishes this line. Display may hold longer until the next cue."""
    fallback = min(display_end, start_ms + max(800, min(MAX_LINE_MS, display_end - start_ms)))
    if not regions:
        return fallback
    sing = None
    last = start_ms
    for region_start, region_end in regions:
        if region_end <= start_ms:
            continue
        if region_start >= display_end:
            break
        if sing is None:
            if region_start > start_ms + 900:
                return fallback
            sing = min(display_end, max(region_end, start_ms + 400) + 80)
            last = region_end
            continue
        if region_start - last > 350:
            break
        sing = min(display_end, region_end + 80)
        last = region_end
    if sing is None:
        return fallback
    return max(start_ms + 400, min(display_end, sing))

def pack_tokens_to_singing(
    cues: list[dict[str, Any]],
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Keep the line on screen until the next cue, but sweep words only while singing."""
    regions = vocal_regions(envelope or [], hop_ms)
    for cue in cues:
        start_ms = int(cue["start_ms"])
        display_end = int(cue["end_ms"])
        sing_end = int(cue.get("sing_end_ms") or line_sing_end(start_ms, display_end, regions))
        cue["sing_end_ms"] = sing_end
        tokens = list(cue.get("tokens") or [])
        if not tokens:
            continue
        spans = energy_token_spans(start_ms, sing_end, len(tokens), envelope or [], hop_ms)
        for token, (left, right) in zip(tokens, spans):
            token["start_ms"] = left
            token["end_ms"] = right
        tokens[0]["start_ms"] = start_ms
        tokens[-1]["end_ms"] = sing_end
    return cues

def hold_lines_until_next(
    bounds: list[dict[str, Any]],
    max_gap_ms: int = HOLD_GAP_MS,
) -> list[dict[str, Any]]:
    """Keep a line on screen through a short breath, not a long instrumental."""
    for index, row in enumerate(bounds[:-1]):
        nxt = int(bounds[index + 1]["start_ms"])
        end = int(row["end_ms"])
        if 0 < nxt - end <= max_gap_ms:
            row["end_ms"] = nxt
    return bounds

def snap_unmatched_to_voice(
    bounds: list[dict[str, Any]],
    regions: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    """If an official fallback sits in a hole, slide it onto the vocal before the next ASR line."""
    if not bounds or not regions:
        return bounds
    for index, row in enumerate(bounds[:-1]):
        nxt = bounds[index + 1]
        if row.get("from_asr") or not nxt.get("from_asr"):
            continue
        start_ms = int(row["start_ms"])
        next_start = int(nxt["start_ms"])
        if _voice_covers(regions, start_ms):
            continue
        onsets = [
            region_start
            for region_start, region_end in regions
            if start_ms < region_start < next_start - 250 and region_end - region_start >= 280
        ]
        if not onsets:
            continue
        onset = onsets[0]
        if onset - start_ms < 400 or onset - start_ms > 8000:
            continue
        row["start_ms"] = onset
        row["end_ms"] = max(onset + MIN_LINE_MS, min(int(row["end_ms"]) + (onset - start_ms), next_start))
    return bounds
