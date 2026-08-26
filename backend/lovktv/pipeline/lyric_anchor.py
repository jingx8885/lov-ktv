"""Refine Whisper line times with lyric-align word spans.

Whisper `align_lines_to_asr` owns the clock (official LRC + ASR offset).
lyric-align only tightens a line when its start agrees with that clock.
"""

from __future__ import annotations

import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_VENDOR = Path(__file__).resolve().parents[3] / "vendor" / "lyric-align" / "src"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from lyric_align.model import Segment, Word  # noqa: E402
from lyric_align.normalize import default_threshold, normalize, similarity  # noqa: E402

from lovktv.pipeline.align import (
    HOLD_GAP_MS,
    MAX_LINE_MS,
    MIN_LINE_MS,
    _usable_asr_words,
    _voice_covers,
    hold_lines_until_next,
    snap_to_onset,
    vocal_regions,
)
from lovktv.pipeline.lyrics import drop_credit_lines

ANCHOR_AGREE_MS = 800
ANCHOR_RESCUE_MS = 2400
OFFICIAL_ALIVE_AFTER_MS = 4500
OFFICIAL_ALIVE_BEFORE_MS = 2500
OFFICIAL_HOLE_BEFORE_MS = 1500
OFFICIAL_HOLE_AFTER_MS = 12000
ONSET_BEFORE_MS = 800
HOLE_THRESHOLD_BUMP = 0.08
EXTEND_GAP_S = 2.0
MAX_EXTEND = 4


def asr_words_to_segments(asr_words: list[dict[str, Any]], gap_ms: int = 600) -> list[Segment]:
    """Rebuild phrase-sized segments from Whisper words.

    Prefer Whisper's own segment ids. CJK models emit character words with
    tiny gaps, so a flat 600ms merge would swallow half the song.
    """
    usable = _usable_asr_words(asr_words)
    if not usable:
        return []
    groups: list[list[dict[str, Any]]] = [[usable[0]]]
    use_ids = all("segment" in item for item in usable)
    for word in usable[1:]:
        prev = groups[-1][-1]
        new_group = (
            word.get("segment") != prev.get("segment")
            if use_ids
            else int(word["start_ms"]) - int(prev["end_ms"]) > gap_ms
        )
        if new_group:
            groups.append([word])
        else:
            groups[-1].append(word)
    segments: list[Segment] = []
    for group in groups:
        words = [
            Word(
                start=int(item["start_ms"]) / 1000,
                end=max(int(item["end_ms"]), int(item["start_ms"]) + 40) / 1000,
                word=str(item.get("text") or ""),
            )
            for item in group
        ]
        segments.append(
            Segment(
                start=words[0].start,
                end=words[-1].end,
                text="".join(item.word for item in words),
                words=words,
            )
        )
    return segments


def _in_official_window(
    start_ms: int,
    official_ms: int | None,
    official_alive: bool,
) -> bool:
    if official_ms is None:
        return True
    if official_alive:
        return official_ms - OFFICIAL_ALIVE_BEFORE_MS <= start_ms <= official_ms + OFFICIAL_ALIVE_AFTER_MS
    return official_ms - OFFICIAL_HOLE_BEFORE_MS <= start_ms <= official_ms + OFFICIAL_HOLE_AFTER_MS


def _segment_from_words(words: list[Word]) -> Segment:
    return Segment(
        start=words[0].start,
        end=words[-1].end,
        text="".join(item.word for item in words),
        words=words,
    )


def _consume_words(words: list[Word], lyric: str) -> tuple[list[Word], list[Word]]:
    """Keep the words this line explains; leftover stays for the next line.

    Prefix matches keep the leading ASR substitution (悲しい for 目まぐるしい).
    Tail matches drop the earlier phrase that belongs to a previous line.
    """
    if not words:
        return [], []
    lyric_norm = normalize(lyric)
    parts = [normalize(item.word) for item in words]
    seg_norm = "".join(parts)
    if not lyric_norm or not seg_norm:
        return words, []
    if len(seg_norm) <= max(int(len(lyric_norm) * 1.35), len(lyric_norm) + 3):
        return words, []
    match = SequenceMatcher(None, lyric_norm, seg_norm).find_longest_match(
        0, len(lyric_norm), 0, len(seg_norm)
    )
    if match.size < 2:
        return words, []
    match_end = match.b + match.size
    # Only treat as a tail if a whole previous line sits in front
    # (入り浸った after どうでも). Hiragana ASR of the same line
    # (どひょうめき…響めき) must keep the leading attack.
    tail = match.b >= len(lyric_norm)
    used: list[Word] = []
    after: list[Word] = []
    pos = 0
    for word, part in zip(words, parts):
        start, end = pos, pos + len(part)
        pos = end
        if tail and end <= match.b:
            continue
        if start >= match_end:
            after.append(word)
        else:
            used.append(word)
    if not used:
        return words, []
    return used, after


def _pick_span(
    segments: list[Segment],
    cursor: int,
    joined: str,
    official: int | None,
    official_alive: bool,
    threshold: float,
    next_text: str = "",
) -> tuple[float, int | None, int | None]:
    need = threshold if (official_alive or official is None) else threshold + HOLE_THRESHOLD_BUMP
    best_score, best_i, best_j = 0.0, None, None
    upper = min(cursor + 8, len(segments))
    for index in range(cursor, upper):
        start_ms = int(segments[index].start * 1000)
        if not _in_official_window(start_ms, official, official_alive):
            continue
        acc: list[Word] = []
        for extra in range(index, min(index + MAX_EXTEND, len(segments))):
            if extra > index and segments[extra].start - segments[extra - 1].end > EXTEND_GAP_S:
                break
            extra_text = segments[extra].text
            if extra > index and next_text:
                if similarity(next_text, extra_text) > similarity(joined, extra_text) + 0.08:
                    break
            acc.extend(segments[extra].words)
            text = "".join(item.word for item in acc)
            score = similarity(joined, text)
            if score > best_score and _match_run_ok(joined, text, official_alive):
                best_score, best_i, best_j = score, index, extra
    if best_i is not None and best_score > need:
        return best_score, best_i, best_j
    return best_score, None, None


def _peel_next_line(
    used: list[Word],
    leftover: list[Word],
    next_lyric: str,
) -> tuple[list[Word], list[Word]]:
    """If this line ate the next lyric's tail (息が), give those words back."""
    if leftover or not used or not next_lyric.strip() or len(used) < 2:
        return used, leftover
    nxt = normalize(next_lyric)
    if len(nxt) < 2:
        return used, leftover
    parts = [normalize(item.word) for item in used]
    acc = ""
    for index in range(len(used) - 1, 0, -1):
        acc = parts[index] + acc
        if similarity(nxt, acc) >= 0.72:
            return used[:index], used[index:]
        if len(acc) > len(nxt) + 3:
            break
    return used, leftover


def _min_display_ms(text: str) -> int:
    n = max(1, len(normalize(text)))
    return min(MAX_LINE_MS, max(MIN_LINE_MS, 220 * n))


def _stretch_short_lines(bounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Borrow time from the next line so a 3-char hook is not a 500ms flash."""
    for index, row in enumerate(bounds[:-1]):
        nxt = bounds[index + 1]
        need = _min_display_ms(str(row.get("text") or ""))
        span = int(row["end_ms"]) - int(row["start_ms"])
        if span >= need:
            continue
        nxt_span = int(nxt["end_ms"]) - int(nxt["start_ms"])
        steal = min(need - span, max(0, nxt_span - MIN_LINE_MS))
        if steal < 80:
            continue
        row["end_ms"] = int(row["end_ms"]) + steal
        nxt["start_ms"] = int(nxt["start_ms"]) + steal
        nxt["end_ms"] = max(nxt["start_ms"] + MIN_LINE_MS, int(nxt["end_ms"]))
    return bounds


def _enforce_monotonic(bounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index in range(1, len(bounds)):
        prev = bounds[index - 1]
        row = bounds[index]
        if row["start_ms"] < prev["end_ms"]:
            if row.get("from_asr") and not prev.get("from_asr"):
                prev["end_ms"] = max(prev["start_ms"] + MIN_LINE_MS, row["start_ms"])
            else:
                row["start_ms"] = prev["end_ms"]
        if prev["end_ms"] > row["start_ms"]:
            prev["end_ms"] = max(prev["start_ms"] + MIN_LINE_MS, row["start_ms"])
        row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, int(row["end_ms"]))
    return bounds


def _match_run_ok(lyric: str, asr_text: str, official_alive: bool) -> bool:
    lyric_norm = normalize(lyric)
    asr_norm = normalize(asr_text)
    match = SequenceMatcher(None, lyric_norm, asr_norm).find_longest_match(
        0, len(lyric_norm), 0, len(asr_norm)
    )
    return match.size >= min(3, max(2, len(lyric_norm)))


def _prev_limit(bounds: list[dict[str, Any]], index: int) -> int:
    if not index:
        return 0
    prev = bounds[index - 1]
    if prev.get("from_asr"):
        return int(prev["end_ms"])
    return int(prev["start_ms"]) + MIN_LINE_MS


def _snap_matched_start(start_ms: int, regions: list[tuple[int, int]]) -> int:
    if not regions:
        return start_ms
    snapped = snap_to_onset(start_ms, regions, search_before=ONSET_BEFORE_MS, search_after=120)
    if 0 <= start_ms - snapped <= ONSET_BEFORE_MS:
        return snapped
    return start_ms


def _fill_unmatched(
    bounds: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    regions: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    for index, row in enumerate(bounds):
        if row.get("from_asr"):
            continue
        official = int(lines[index]["ms"]) if lines[index].get("ms") is not None else None
        nxt = next((item["start_ms"] for item in bounds[index + 1:] if item.get("from_asr")), None)
        prev_limit = _prev_limit(bounds, index)
        if official is not None and _voice_covers(regions, official):
            start_ms = max(prev_limit, official)
        elif official is not None and regions:
            lo = max(official, prev_limit)
            hi = (nxt if nxt is not None else lo + 20_000) - 250
            onsets = [
                start
                for start, end in regions
                if lo < start < hi and end - start >= 280
            ]
            if onsets and onsets[0] - official <= 8000:
                start_ms = onsets[0]
            else:
                start_ms = max(prev_limit, official)
        elif nxt is not None:
            start_ms = prev_limit + max(MIN_LINE_MS, (nxt - prev_limit) // 3)
        else:
            start_ms = prev_limit
        end_ms = nxt if nxt is not None else start_ms + MIN_LINE_MS * 2
        if nxt is None and official is not None and lines[index].get("end_ms") is not None:
            end_ms = max(start_ms + MIN_LINE_MS, int(lines[index]["end_ms"]))
        next_official = (
            int(lines[index + 1]["ms"])
            if index + 1 < len(lines) and lines[index + 1].get("ms") is not None
            else None
        )
        if next_official is not None and start_ms < next_official < end_ms:
            end_ms = next_official
        end_ms = min(end_ms, start_ms + MAX_LINE_MS)
        if nxt is None or (nxt is not None and nxt - start_ms > MAX_LINE_MS):
            end_ms = min(end_ms, start_ms + 4000)
        row["start_ms"] = max(0, start_ms)
        row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, end_ms)
    for index, row in enumerate(bounds[:-1]):
        nxt = bounds[index + 1]
        if row["end_ms"] > nxt["start_ms"]:
            row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, nxt["start_ms"])
        if 0 < nxt["start_ms"] - row["end_ms"] <= HOLD_GAP_MS:
            row["end_ms"] = nxt["start_ms"]
    return bounds


def merge_whisper_and_anchor(
    whisper_bounds: list[dict[str, Any]],
    anchor_bounds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep Whisper starts; take lyric-align spans only when they sit on the same line."""
    if not whisper_bounds:
        return list(whisper_bounds)
    if not anchor_bounds:
        return [dict(row) for row in whisper_bounds]
    merged: list[dict[str, Any]] = []
    for index, whisper in enumerate(whisper_bounds):
        row = dict(whisper)
        if index >= len(anchor_bounds):
            merged.append(row)
            continue
        anchor = anchor_bounds[index]
        if not anchor.get("from_asr"):
            merged.append(row)
            continue
        delta = abs(int(anchor["start_ms"]) - int(whisper["start_ms"]))
        adopt = delta <= ANCHOR_AGREE_MS or (
            not whisper.get("from_asr") and delta <= ANCHOR_RESCUE_MS
        )
        if not adopt:
            merged.append(row)
            continue
        nxt = int(whisper_bounds[index + 1]["start_ms"]) if index + 1 < len(whisper_bounds) else None
        start_ms = int(anchor["start_ms"])
        if nxt is not None and start_ms >= nxt and whisper.get("from_asr"):
            merged.append(row)
            continue
        end_ms = int(anchor["end_ms"])
        # Whisper often starts the next line on this line's tail. A rescued
        # match must keep its words; push the next start later instead.
        if nxt is not None and whisper.get("from_asr"):
            end_ms = min(end_ms, nxt)
        row["start_ms"] = max(0, start_ms)
        row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, end_ms)
        row["from_asr"] = True
        merged.append(row)
    for index in range(1, len(merged)):
        prev = merged[index - 1]
        row = merged[index]
        if row["start_ms"] < prev["end_ms"]:
            row["start_ms"] = int(prev["end_ms"])
        row["end_ms"] = max(row["start_ms"] + MIN_LINE_MS, int(row["end_ms"]))
    return hold_lines_until_next(merged)


def align_lines_with_anchor(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    envelope: list[float] | None = None,
    hop_ms: int = 20,
) -> list[dict[str, Any]]:
    """Place known lines on ASR segments; official LRC only gates and fills gaps."""
    kept = drop_credit_lines(lines, language)
    kept = [item for item in kept if str(item.get("text") or "").strip()]
    segments = asr_words_to_segments(asr_words)
    if not kept:
        return []
    texts = [str(item.get("text") or "") for item in kept]
    if not segments:
        return [
            {
                "text": text,
                "start_ms": int(item["ms"]) if item.get("ms") is not None else 0,
                "end_ms": int(item["end_ms"]) if item.get("end_ms") is not None else int(item.get("ms") or 0) + MIN_LINE_MS,
                "from_asr": False,
            }
            for item, text in zip(kept, texts)
        ]

    threshold = default_threshold(texts)
    regions = vocal_regions(envelope or [], hop_ms) if envelope else []
    bounds: list[dict[str, Any]] = []
    cursor = 0
    for line_index, line in enumerate(kept):
        text = str(line.get("text") or "")
        next_text = str(kept[line_index + 1].get("text") or "") if line_index + 1 < len(kept) else ""
        official = int(line["ms"]) if line.get("ms") is not None else None
        official_alive = official is not None and _voice_covers(regions, official)
        best_score, best_i, best_j = _pick_span(
            segments, cursor, text, official, official_alive, threshold, next_text
        )
        if best_i is not None and best_j is not None:
            words: list[Word] = []
            for index in range(best_i, best_j + 1):
                words.extend(segments[index].words)
            used, leftover = _consume_words(words, text)
            leftover_text = "".join(item.word for item in leftover)
            if leftover and len(normalize(leftover_text)) <= 3:
                if not next_text or similarity(next_text, leftover_text) < 0.55:
                    used = used + leftover
                    leftover = []
            used, leftover = _peel_next_line(used, leftover, next_text)
            del segments[best_i : best_j + 1]
            if leftover:
                segments.insert(best_i, _segment_from_words(leftover))
                cursor = best_i
            else:
                cursor = best_i
            start_ms = int(used[0].start * 1000) if used else int(words[0].start * 1000)
            end_ms = int(used[-1].end * 1000) if used else int(words[-1].end * 1000)
            start_ms = _snap_matched_start(start_ms, regions)
            if bounds:
                start_ms = max(start_ms, int(bounds[-1]["end_ms"]))
            bounds.append(
                {
                    "text": str(line.get("text") or text),
                    "start_ms": max(0, start_ms),
                    "end_ms": max(start_ms + MIN_LINE_MS, end_ms),
                    "from_asr": True,
                    "score": best_score,
                }
            )
        else:
            bounds.append(
                {
                    "text": str(line.get("text") or text),
                    "start_ms": int(line["ms"]) if line.get("ms") is not None else 0,
                    "end_ms": int(line["end_ms"]) if line.get("end_ms") is not None else (int(line["ms"]) if line.get("ms") is not None else 0) + MIN_LINE_MS,
                    "from_asr": False,
                    "score": best_score,
                }
            )
    _fill_unmatched(bounds, kept, regions)
    _enforce_monotonic(bounds)
    hold_lines_until_next(bounds, max_gap_ms=8000)
    _stretch_short_lines(bounds)
    _enforce_monotonic(bounds)
    return hold_lines_until_next(bounds, max_gap_ms=8000)
