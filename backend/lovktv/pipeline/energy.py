"""Vocal-energy based line boundary refinement."""

from __future__ import annotations

from typing import Any

from lovktv.pipeline.audio import snap_to_onset, vocal_regions
from lovktv.pipeline.constants import *
from lovktv.pipeline.bounds import _voice_covers, hold_lines_until_next
from lovktv.pipeline.matching import vocal_phrases

def _vocal_end_near(start_ms: int, regions: list[tuple[int, int]], limit_ms: int = MAX_LINE_MS) -> int:
    """End the line at the vocal burst covering this LRC start, not the next verse."""
    end_ms = start_ms + 4000
    for region_start, region_end in regions:
        if region_end <= start_ms:
            continue
        if region_start > start_ms + 1200:
            break
        end_ms = max(end_ms, min(region_end + 160, start_ms + limit_ms))
    return min(end_ms, start_ms + limit_ms)

def energy_line_bounds(
    text_bounds: list[dict[str, Any]],
    envelope: list[float],
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Suggest onset-based starts/ends from the current text clock."""
    if not text_bounds or not envelope:
        return []
    regions = vocal_regions(envelope, hop_ms)
    phrases = vocal_phrases(regions) or regions
    if not regions:
        return []
    work = [
        {"text": str(row.get("text") or ""), "ms": int(row["start_ms"]), "end_ms": int(row["end_ms"])}
        for row in text_bounds
    ]
    suggested = _finalize_line_bounds(work, phrases, 0)
    for index, row in enumerate(suggested):
        if text_bounds[index].get("from_asr"):
            continue
        start_ms = int(row["start_ms"])
        if _voice_covers(regions, start_ms):
            continue
        nxt = int(suggested[index + 1]["start_ms"]) if index + 1 < len(suggested) else start_ms + 20_000
        onsets = [
            region_start
            for region_start, region_end in regions
            if start_ms < region_start < nxt - 250 and region_end - region_start >= 280
        ]
        if not onsets:
            continue
        onset = onsets[0]
        if not (ENERGY_HOLE_MIN_MS <= onset - start_ms <= ENERGY_HOLE_MAX_MS):
            continue
        if nxt - onset < ENERGY_NEXT_GUARD_MS and nxt - onset <= onset - start_ms:
            continue
        row["start_ms"] = onset
        row["end_ms"] = max(onset + MIN_LINE_MS, min(int(row["end_ms"]) + (onset - start_ms), nxt))
    return suggested

def merge_with_energy(
    text_bounds: list[dict[str, Any]],
    envelope: list[float] | None,
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Keep ASR hits; snap unmatched lines onto nearby vocal onsets."""
    if not text_bounds or not envelope:
        return [dict(row) for row in text_bounds]
    energy_bounds = energy_line_bounds(text_bounds, envelope, hop_ms)
    if not energy_bounds:
        return [dict(row) for row in text_bounds]
    regions = vocal_regions(envelope, hop_ms)
    merged: list[dict[str, Any]] = []
    for index, text in enumerate(text_bounds):
        row = dict(text)
        energy = energy_bounds[index] if index < len(energy_bounds) else None
        nxt = int(text_bounds[index + 1]["start_ms"]) if index + 1 < len(text_bounds) else None
        if text.get("from_asr"):
            if regions:
                snapped = snap_to_onset(
                    int(row["start_ms"]),
                    regions,
                    search_before=ENERGY_ASR_SNAP_MS,
                    search_after=80,
                )
                if 0 <= int(row["start_ms"]) - snapped <= ENERGY_ASR_SNAP_MS:
                    if nxt is None or snapped < nxt:
                        row["start_ms"] = snapped
            merged.append(row)
            continue
        if energy is None:
            merged.append(row)
            continue
        energy_start = int(energy["start_ms"])
        if nxt is not None and energy_start >= nxt:
            merged.append(row)
            continue
        delta = abs(energy_start - int(row["start_ms"]))
        in_hole = bool(regions) and not _voice_covers(regions, int(row["start_ms"]))
        near_next = nxt is not None and nxt - energy_start < ENERGY_NEXT_GUARD_MS
        adopt = delta <= ENERGY_AGREE_MS or (
            in_hole
            and ENERGY_HOLE_MIN_MS <= energy_start - int(row["start_ms"]) <= ENERGY_HOLE_MAX_MS
            and not near_next
        )
        if adopt:
            row["start_ms"] = max(0, energy_start)
            end_ms = int(energy["end_ms"])
            if nxt is not None:
                end_ms = min(end_ms, nxt)
            row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, end_ms)
        merged.append(row)
    for index in range(1, len(merged)):
        prev = merged[index - 1]
        row = merged[index]
        if row["start_ms"] < prev["end_ms"]:
            row["start_ms"] = int(prev["end_ms"])
        row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, int(row["end_ms"]))
    return hold_lines_until_next(merged)

def guard_early_next_starts(
    bounds: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    envelope: list[float] | None,
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Keep the current line up when the next stamp is still ahead and has voice.

    Whisper often parks the next line on the last syllable of this one.
    Official LRC in a hole is left alone so late onsets can still rescue.
    """
    if not bounds or not envelope or len(bounds) < 2:
        return [dict(row) for row in bounds]
    regions = vocal_regions(envelope, hop_ms)
    if not regions:
        return [dict(row) for row in bounds]
    if len(lines) == len(bounds):
        official = [int(item["ms"]) if item.get("ms") is not None else None for item in lines]
    else:
        official = []
        cursor = 0
        for row in bounds:
            stamp = None
            while cursor < len(lines):
                item = lines[cursor]
                cursor += 1
                if str(item.get("text") or "") == str(row.get("text") or ""):
                    stamp = int(item["ms"]) if item.get("ms") is not None else None
                    break
            official.append(stamp)
    out = [dict(row) for row in bounds]
    for index, row in enumerate(out[:-1]):
        nxt_off = official[index + 1] if index + 1 < len(official) else None
        if nxt_off is None:
            continue
        nxt = out[index + 1]
        early = nxt_off - int(nxt["start_ms"])
        if early <= EARLY_NEXT_SLACK_MS:
            continue
        if not _voice_covers(regions, nxt_off):
            continue
        if _voice_covers(regions, int(nxt["start_ms"])) and early < EARLY_NEXT_FORCE_MS:
            continue
        start_ms = snap_to_onset(nxt_off, regions, search_before=400, search_after=500)
        if start_ms < int(row["start_ms"]) + MIN_LINE_MS:
            continue
        nxt["start_ms"] = start_ms
        nxt["end_ms"] = max(start_ms + MIN_LINE_MS, int(nxt["end_ms"]))
        row["end_ms"] = max(int(row["end_ms"]), start_ms)
    for index in range(1, len(out)):
        prev = out[index - 1]
        row = out[index]
        if row["start_ms"] < prev["end_ms"]:
            row["start_ms"] = int(prev["end_ms"])
        row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, int(row["end_ms"]))
    return hold_lines_until_next(out)

def _finalize_line_bounds(
    lines: list[dict[str, Any]],
    regions: list[tuple[int, int]],
    duration_ms: int,
) -> list[dict[str, Any]]:
    """Keep official LRC starts. Voice only trims long instrumental gaps."""
    starts: list[int] = []
    for line in lines:
        raw = line.get("ms")
        starts.append(int(raw) if raw is not None else max(0, int(line.get("end_ms") or 1000) - 1000))
    for index in range(1, len(starts)):
        starts[index] = max(starts[index], starts[index - 1] + 80)
    bounds: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        start_ms = max(0, starts[index])
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        explicit = line.get("end_ms")
        if explicit is not None:
            end_ms = int(explicit)
        elif next_start is not None and next_start - start_ms <= MAX_LINE_MS:
            end_ms = next_start
        else:
            end_ms = _vocal_end_near(start_ms, regions)
            if next_start is not None:
                end_ms = min(end_ms, next_start)
        end_ms = max(start_ms + 200, end_ms)
        if next_start is not None and next_start - start_ms > MAX_LINE_MS:
            end_ms = min(end_ms, start_ms + MAX_LINE_MS)
        elif duration_ms and next_start is None:
            end_ms = min(end_ms, start_ms + MAX_LINE_MS, duration_ms)
        bounds.append({"text": line["text"], "start_ms": start_ms, "end_ms": end_ms})
    return hold_lines_until_next(bounds)

def nearest_onset(
    target_ms: int,
    regions: list[tuple[int, int]],
    before_ms: int = 600,
    after_ms: int = 600,
    min_ms: int = 280,
) -> int | None:
    best = None
    best_delta = 10**9
    for start_ms, end_ms in regions:
        if end_ms - start_ms < min_ms:
            continue
        if target_ms - before_ms <= start_ms <= target_ms + after_ms:
            delta = abs(start_ms - target_ms)
            if delta < best_delta:
                best = start_ms
                best_delta = delta
    return best

def first_onset_between(
    lo_ms: int,
    hi_ms: int,
    regions: list[tuple[int, int]],
    min_ms: int = 280,
) -> int | None:
    for start_ms, end_ms in regions:
        if end_ms - start_ms < min_ms:
            continue
        if lo_ms < start_ms < hi_ms:
            return start_ms
    return None

def consensus_line_start(
    official_ms: int,
    asr_start: int | None,
    regions: list[tuple[int, int]],
    next_ms: int | None,
    prev_end: int,
) -> tuple[int, bool]:
    """Override official LRC only when Whisper and voice onset agree, or the stamp is silent."""
    start_ms = official_ms
    from_asr = False
    hi = (next_ms - 250) if next_ms is not None else official_ms + 12_000
    onset_near = nearest_onset(official_ms, regions) if regions else None
    onset_after = (
        first_onset_between(max(official_ms + 400, prev_end), hi, regions) if regions else None
    )
    if asr_start is not None and regions:
        asr_onset = nearest_onset(asr_start, regions, 500, 400)
        if asr_onset is not None and abs(asr_start - asr_onset) <= 800 and abs(asr_start - official_ms) > 400:
            if asr_start >= prev_end and (next_ms is None or asr_start < next_ms):
                return asr_onset if 0 <= asr_start - asr_onset <= 400 else asr_start, True
    if asr_start is not None and onset_near is None and asr_start - official_ms > 400:
        if asr_start >= prev_end and (next_ms is None or asr_start < next_ms):
            return asr_start, True
    if onset_near is not None:
        if 0 <= official_ms - onset_near <= 400:
            return official_ms, False
        if 0 <= onset_near - official_ms <= 500:
            return onset_near, False
    if onset_near is None and onset_after is not None:
        if asr_start is not None and abs(asr_start - onset_after) <= 800:
            return onset_after, True
        if ENERGY_HOLE_MIN_MS <= onset_after - official_ms <= ENERGY_HOLE_MAX_MS:
            if next_ms is None or next_ms - onset_after >= ENERGY_NEXT_GUARD_MS or next_ms - onset_after > onset_after - official_ms:
                return onset_after, False
    return start_ms, from_asr

def snap_holes_to_voice(
    bounds: list[dict[str, Any]],
    regions: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    """Slide an official stamp out of silence onto the next vocal before the next line."""
    if not bounds or not regions:
        return bounds
    for index, row in enumerate(bounds):
        if row.get("from_asr"):
            continue
        start_ms = int(row["start_ms"])
        if _voice_covers(regions, start_ms):
            continue
        nxt = int(bounds[index + 1]["start_ms"]) if index + 1 < len(bounds) else start_ms + 20_000
        onsets = [
            region_start
            for region_start, region_end in regions
            if start_ms < region_start < nxt - 250 and region_end - region_start >= 280
        ]
        if not onsets:
            continue
        onset = onsets[0]
        if not (ENERGY_HOLE_MIN_MS <= onset - start_ms <= ENERGY_HOLE_MAX_MS):
            continue
        if nxt - onset < ENERGY_NEXT_GUARD_MS and nxt - onset <= onset - start_ms:
            continue
        row["start_ms"] = onset
        row["end_ms"] = max(onset + MIN_LINE_MS, min(int(row["end_ms"]) + (onset - start_ms), nxt))
    return bounds
