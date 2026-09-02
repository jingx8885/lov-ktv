"""Orchestrate the lyric-alignment pipeline components."""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

from lovktv.pipeline.audio import (
    energy_token_spans as _energy_token_spans,
)
from lovktv.pipeline.audio import (
    extract_envelope as _extract_envelope,
)
from lovktv.pipeline.audio import (
    probe_duration_ms as _probe_duration_ms,
)
from lovktv.pipeline.audio import (
    vocal_regions as _vocal_regions,
)
from lovktv.pipeline.bounds import align_lines_to_asr as _align_lines_to_asr
from lovktv.pipeline.bounds import assign_plain_lines as _assign_plain_lines
from lovktv.pipeline.clock import (
    align_lines_official_clock as _align_lines_official_clock,
)
from lovktv.pipeline.constants import HOP_MS
from lovktv.pipeline.energy import _finalize_line_bounds
from lovktv.pipeline.energy import merge_with_energy as _merge_with_energy
from lovktv.pipeline.language import detect_language
from lovktv.pipeline.lyrics import (
    build_cue,
    drop_credit_lines,
    prepare_lyric_lines,
    timeline_from_lrc,
    tokenize,
)
from lovktv.pipeline.matching import (
    asr_token_spans as _asr_token_spans,
)
from lovktv.pipeline.matching import _usable_asr_words
from lovktv.pipeline.matching import (
    estimate_lrc_offset as _estimate_lrc_offset,
)
from lovktv.pipeline.matching import (
    vocal_phrases as _vocal_phrases,
)


def align_lyrics(
    lines: list[dict[str, Any]],
    language: str | None = None,
    audio_path: Path | None = None,
    duration_ms: int | None = None,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
    asr_words: list[dict[str, Any]] | None = None,
    agent_matches: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Return karaoke timeline anchored to voice when possible."""
    joined = "".join(str(item.get("text") or "") for item in lines)
    lang = detect_language(joined, language)
    lines = prepare_lyric_lines(lines, lang)
    timed = [item for item in lines if item.get("ms") is not None]
    plain = [str(item.get("text") or "") for item in lines if item.get("ms") is None]

    if envelope is None and audio_path is not None:
        envelope, hop_ms = _extract_envelope(audio_path, hop_ms)
        duration_ms = duration_ms or _probe_duration_ms(audio_path)

    if not lines:
        return {
            "language": lang,
            "alignment": "empty",
            "alignment_source": "",
            "cues": [],
        }

    if asr_words:
        timed_lines = [item for item in lines if item.get("ms") is not None]
        used_asr_clock = False
        used_drift_clock = False
        used_reordered_clock = False
        reordered = _align_reordered_lines(lines, asr_words, lang, agent_matches, duration_ms)
        if reordered is not None:
            bounds = reordered
            used_reordered_clock = True
        elif timed_lines:
            drift_clock = _align_version_drift(
                lines,
                asr_words,
                lang,
                agent_matches,
                duration_ms,
            )
            if drift_clock is not None:
                bounds = drift_clock
                used_drift_clock = True
            else:
                bounds = _align_lines_official_clock(
                    lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms
                )
                asr_clock = _prefer_asr_clock(
                    lines, asr_words, lang, envelope, hop_ms, duration_ms
                )
                if asr_clock is not None:
                    bounds = asr_clock
                    used_asr_clock = True
        else:
            from lovktv.pipeline.lyric_anchor import (
                align_lines_with_anchor,
                merge_whisper_and_anchor,
            )

            whisper_bounds = _align_lines_to_asr(
                lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms
            )
            if not whisper_bounds:
                bounds = []
            else:
                bounds = _merge_with_energy(
                    merge_whisper_and_anchor(
                        whisper_bounds,
                        align_lines_with_anchor(
                            lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms
                        ),
                    ),
                    envelope,
                    hop_ms,
                )
        if bounds:
            agent_count = 0 if (used_drift_clock or used_reordered_clock) else _apply_agent_matches(
                bounds, lines, asr_words, agent_matches, lang
            )
            if used_drift_clock or used_reordered_clock:
                agent_count = 1
            cues = []
            for row in bounds:
                pieces = tokenize(str(row["text"]), lang)
                spans = _asr_token_spans(
                    pieces, row["start_ms"], row["end_ms"], asr_words, lang
                )
                if not spans:
                    spans = _energy_token_spans(
                        row["start_ms"],
                        row["end_ms"],
                        len(pieces),
                        envelope or [],
                        hop_ms,
                    )
                cue = build_cue(
                    str(row["text"]), row["start_ms"], row["end_ms"], lang, spans
                )
                if cue:
                    cues.append(cue)
            return {
                "language": lang,
                "alignment": "agent" if agent_count else ("asr" if used_asr_clock else ("lrc" if timed_lines else "asr")),
                "alignment_source": (
                    "agent+whisper-drift"
                    if used_drift_clock
                    else ("agent+whisper-reordered" if used_reordered_clock else ("agent+whisper" if agent_count else ("whisper" if used_asr_clock or not timed_lines else "official")))
                ),
                "cues": cues,
            }

    if envelope:
        regions = _vocal_regions(envelope, hop_ms)
        phrases = _vocal_phrases(regions)
        work: list[dict[str, Any]] = []
        if plain and not timed:
            duration = duration_ms or 60_000
            work = _assign_plain_lines(plain, phrases or regions, duration)
        elif timed:
            shift = _estimate_lrc_offset(timed, phrases)
            shifted = []
            for item in timed:
                row = dict(item)
                row["ms"] = int(item["ms"]) + shift
                if item.get("end_ms") is not None:
                    row["end_ms"] = int(item["end_ms"]) + shift
                shifted.append(row)
            work = shifted
        duration = duration_ms or (int(work[-1]["ms"]) + 4000 if work else 0)
        bounds = _finalize_line_bounds(work, phrases or regions, duration)
        cues = []
        for row in bounds:
            pieces = tokenize(str(row["text"]), lang)
            spans = _energy_token_spans(
                row["start_ms"], row["end_ms"], len(pieces), envelope, hop_ms
            )
            cue = build_cue(
                str(row["text"]), row["start_ms"], row["end_ms"], lang, spans
            )
            if cue:
                cues.append(cue)
        source = str(audio_path.name) if audio_path else "envelope"
        return {
            "language": lang,
            "alignment": "onset",
            "alignment_source": source,
            "cues": cues,
        }


    if timed and all(item.get("ms") is not None for item in lines):
        timeline = timeline_from_lrc(lines, lang, duration_ms=duration_ms)
        timeline["alignment"] = "lrc-interp"
        timeline["alignment_source"] = ""
        return timeline

    duration = duration_ms or max(len(lines) * 4000, 4000)
    texts = [str(item.get("text") or "") for item in lines if item.get("text")]
    assigned = _assign_plain_lines(texts, [], duration)
    timeline = timeline_from_lrc(assigned, lang, duration_ms=duration)
    timeline["alignment"] = "duration-fallback"
    timeline["alignment_source"] = ""
    return timeline


def _align_reordered_lines(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    matches: list[dict[str, int]] | None,
    duration_ms: int | None,
) -> list[dict[str, Any]] | None:
    """Build a timeline when an edited video sings lines out of LRC order."""
    if not matches or not asr_words:
        return None
    kept = [
        item
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    words = _usable_asr_words(asr_words)
    if not kept or not words:
        return None
    rows: list[dict[str, Any]] = []
    seen_lyrics: set[int] = set()
    seen_words: set[int] = set()
    previous_lyric: int | None = None
    reordered = False
    for match in matches:
        try:
            lyric_index = int(match["lyric"]) - 1
            start_index = int(match["from"]) - 1
            end_index = int(match["to"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= lyric_index < len(kept) and 0 <= start_index <= end_index < len(words)):
            continue
        if lyric_index in seen_lyrics or any(i in seen_words for i in range(start_index, end_index + 1)):
            continue
        if previous_lyric is not None and lyric_index < previous_lyric:
            reordered = True
        previous_lyric = lyric_index
        seen_lyrics.add(lyric_index)
        seen_words.update(range(start_index, end_index + 1))
        start_ms = int(words[start_index].get("start_ms") or 0)
        end_ms = max(start_ms + 40, int(words[end_index].get("end_ms") or start_ms + 40))
        # A single line landing tens of seconds away from its LRC stamp is a
        # strong signal of an edited/reordered video even when the model still
        # returns lyric numbers monotonically (it may simply skip the moved
        # block).  Small global offsets remain on the existing clock paths.
        official_ms = kept[lyric_index].get("ms")
        if official_ms is not None and abs(start_ms - int(official_ms)) >= 40_000:
            reordered = True
        rows.append({
            "text": str(kept[lyric_index].get("text") or ""),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "from_asr": True,
        })
    # Sparse monotonic matches continue through the existing drift/official
    # logic.  Require a genuine order inversion before switching clocks.
    if not reordered or len(rows) < 3:
        return None
    # Fill lyric rows that the ASR could not confidently spell.  Interpolate
    # their clock between the nearest matched lyric indices; this preserves a
    # complete karaoke track while keeping the matched Grok word timestamps
    # authoritative.  The interpolation is especially useful when a short
    # edit omits a few words from one remote chunk.
    matched_by_index = {
        int(match["lyric"]) - 1: row
        for match, row in zip(matches, rows)
        if isinstance(match, dict) and "lyric" in match
    }
    # Rebuild the map from validated rows (the zip above is unsafe when the
    # agent returned an invalid/overlapping row that was skipped).
    matched_by_index = {}
    for match in matches:
        try:
            idx = int(match["lyric"]) - 1
            start = int(words[int(match["from"]) - 1].get("start_ms") or 0)
            end = max(start + 40, int(words[int(match["to"]) - 1].get("end_ms") or start + 40))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if idx in seen_lyrics:
            matched_by_index[idx] = {"text": str(kept[idx].get("text") or ""), "start_ms": start, "end_ms": end, "from_asr": True}
    for index, item in enumerate(kept):
        if index in matched_by_index:
            continue
        lower = max((key for key in matched_by_index if key < index), default=None)
        upper = min((key for key in matched_by_index if key > index), default=None)
        # When the upper anchor itself is a moved block (large ASR↔LRC
        # discrepancy), interpolating preceding LRC rows would place them
        # before the moved verse. Leave those rows unmatched until a later
        # concrete occurrence is found instead of displaying them early.
        if upper is not None:
            upper_official = kept[upper].get("ms")
            if upper_official is not None and abs(int(matched_by_index[upper]["start_ms"]) - int(upper_official)) >= 40_000 and index < upper:
                continue
        if lower is not None and upper is not None:
            left = matched_by_index[lower]["start_ms"]
            right = matched_by_index[upper]["start_ms"]
            ratio = (index - lower) / max(1, upper - lower)
            start = int(round(left + ratio * (right - left)))
        elif lower is not None:
            start = int(matched_by_index[lower]["end_ms"]) + max(120, (index - lower) * 700)
        elif upper is not None:
            start = max(0, int(matched_by_index[upper]["start_ms"]) - max(120, (upper - index) * 700))
        else:
            continue
        matched_by_index[index] = {"text": str(item.get("text") or ""), "start_ms": start, "end_ms": start + 500, "from_asr": False}
        rows.append(matched_by_index[index])
    rows = list(matched_by_index.values())
    rows.sort(key=lambda row: (int(row["start_ms"]), int(row["end_ms"])))
    bounds: list[dict[str, Any]] = []
    for row in rows:
        start_ms = max(0, int(row["start_ms"]))
        end_ms = max(start_ms + 40, int(row["end_ms"]))
        if bounds and start_ms < int(bounds[-1]["end_ms"]):
            start_ms = int(bounds[-1]["end_ms"])
            if start_ms >= end_ms:
                continue
        if duration_ms:
            start_ms = min(start_ms, max(0, int(duration_ms) - 200))
            end_ms = min(int(duration_ms), max(start_ms + 40, end_ms))
        bounds.append({"text": row["text"], "start_ms": start_ms, "end_ms": end_ms, "from_asr": True})
    return bounds or None


def _apply_agent_matches(
    bounds: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    matches: list[dict[str, int]] | None,
    language: str,
) -> int:
    """Overlay validated agent-selected ASR spans on deterministic bounds."""
    if not bounds or not matches or not asr_words:
        return 0
    from lovktv.pipeline.matching import _usable_asr_words

    kept = [
        item
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    words = _usable_asr_words(asr_words)
    if len(kept) != len(bounds) or not words:
        return 0
    applied = 0
    for match in matches:
        try:
            line_index = int(match["lyric"]) - 1
            start_index = int(match["from"]) - 1
            end_index = int(match["to"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= line_index < len(bounds) and 0 <= start_index <= end_index < len(words)):
            continue
        start_ms = int(words[start_index].get("start_ms") or 0)
        end_ms = int(words[end_index].get("end_ms") or start_ms + 40)
        if line_index and start_ms < int(bounds[line_index - 1]["start_ms"]):
            continue
        if end_ms <= start_ms:
            continue
        bounds[line_index]["start_ms"] = max(0, start_ms)
        bounds[line_index]["end_ms"] = max(start_ms + 40, end_ms)
        bounds[line_index]["from_asr"] = True
        applied += 1
    if applied:
        for index in range(1, len(bounds)):
            bounds[index]["start_ms"] = max(
                int(bounds[index]["start_ms"]), int(bounds[index - 1]["end_ms"])
            )
            bounds[index]["end_ms"] = max(
                int(bounds[index]["start_ms"]) + 40, int(bounds[index]["end_ms"])
            )
    return applied


def _align_version_drift(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    matches: list[dict[str, int]] | None,
    duration_ms: int | None,
) -> list[dict[str, Any]] | None:
    """Build a piecewise ASR clock when LRC and media are different edits.

    Agent matches are treated as sparse anchors.  Unmatched lyric rows are
    interpolated between neighboring anchors using their original LRC spacing;
    this keeps a missed line from pushing every later ASR hit forward.
    """
    if not matches or not asr_words:
        return None
    kept = [
        item
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    words = _usable_asr_words(asr_words)
    if len(kept) != len(lines) or not words:
        return None

    anchors: dict[int, tuple[int, int]] = {}
    for row in matches:
        try:
            line_index = int(row["lyric"]) - 1
            start_index = int(row["from"]) - 1
            end_index = int(row["to"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= line_index < len(kept) and 0 <= start_index <= end_index < len(words)):
            continue
        start_ms = int(words[start_index].get("start_ms") or 0)
        end_ms = int(words[end_index].get("end_ms") or start_ms + 40)
        if end_ms <= start_ms:
            continue
        if anchors and line_index <= max(anchors):
            continue
        if anchors and start_ms < anchors[max(anchors)][0]:
            continue
        anchors[line_index] = (start_ms, max(start_ms + 40, end_ms))
    if len(anchors) < 3:
        return None

    # If the first lyric lines have no reliable ASR anchor, the transcript
    # usually starts with an intro, dialogue, or other non-lyric material.
    # Treating a later anchor as a different-version clock would project those
    # missed lines from 0 ms and destroy their trusted official LRC timing.
    # Version-drift correction is only safe when the recording is anchored
    # from the first lyric line onward.
    if min(anchors) != 0:
        return None

    # A long official lead-in followed by an ASR match at 0 ms is the common
    # "broadcast/intro omitted by ASR" shape.  Keep the official clock when
    # we know the real media duration; an alternative edit is not enough
    # evidence to erase a trusted lead-in.
    first_lrc = int(kept[0].get("ms") or 0)
    first_asr = anchors[0][0] if 0 in anchors else 0
    if duration_ms and duration_ms >= 120_000 and first_lrc >= 10_000 and first_asr < 3_000:
        return None

    # A near-complete lexical match is strong evidence that the existing
    # official clock belongs to this recording.  Do not replace good timing
    # merely because the file has a long tail, intro, or credits difference.
    coverage = len(anchors) / max(1, len(kept))
    if coverage >= 0.8:
        return None

    lrc_times = [
        int(item["ms"]) if item.get("ms") is not None else None for item in kept
    ]
    lrc_values = [value for value in lrc_times if value is not None]
    media_end = int(duration_ms or 0)
    lrc_end = max(lrc_values or [0])
    duration_mismatch = bool(
        media_end
        and abs(lrc_end - media_end) > max(20_000, int(media_end * 0.08))
    )
    offsets = [
        anchors[index][0] - lrc_times[index]
        for index in anchors
        if lrc_times[index] is not None
    ]
    large_offset = len(offsets) >= 3 and abs(median(offsets)) >= 5_000
    if not (duration_mismatch or large_offset):
        return None

    def lrc_position(index: int) -> float:
        value = lrc_times[index]
        if value is not None:
            return float(value)
        prev = next((lrc_times[i] for i in range(index - 1, -1, -1) if lrc_times[i] is not None), None)
        nxt = next((lrc_times[i] for i in range(index + 1, len(lrc_times)) if lrc_times[i] is not None), None)
        if prev is not None and nxt is not None:
            return (prev + nxt) / 2
        if prev is not None:
            return float(prev + 1000)
        if nxt is not None:
            return float(nxt - 1000)
        return float(index * 1000)

    def projected_start(index: int) -> int:
        if index in anchors:
            return anchors[index][0]
        position = lrc_position(index)
        before = max((i for i in anchors if i < index), default=None)
        after = min((i for i in anchors if i > index), default=None)
        if before is not None and after is not None:
            left_pos, right_pos = lrc_position(before), lrc_position(after)
            span = right_pos - left_pos
            ratio = (position - left_pos) / span if span > 0 else (index - before) / max(1, after - before)
            return int(round(anchors[before][0] + ratio * (anchors[after][0] - anchors[before][0])))
        if before is not None:
            if media_end and after is None:
                remaining = max(1, len(kept) - 1 - before)
                ratio = (index - before) / remaining
                return int(round(anchors[before][0] + ratio * (media_end - anchors[before][0])))
            return int(round(anchors[before][0] + (position - lrc_position(before))))
        if after is not None:
            if media_end and before is None:
                remaining = max(1, after)
                ratio = index / remaining
                return int(round(ratio * anchors[after][0]))
            return int(round(anchors[after][0] - (lrc_position(after) - position)))
        return int(round(position))

    starts = [projected_start(index) for index in range(len(kept))]
    bounds: list[dict[str, Any]] = []
    for index, item in enumerate(kept):
        start_ms = max(0, starts[index])
        if index in anchors:
            end_ms = anchors[index][1]
            from_asr = True
        else:
            next_start = starts[index + 1] if index + 1 < len(starts) else start_ms + 1800
            end_ms = max(start_ms + 40, next_start)
            from_asr = False
        if bounds and start_ms < int(bounds[-1]["end_ms"]):
            bounds[-1]["end_ms"] = max(int(bounds[-1]["start_ms"]) + 40, start_ms)
        end_ms = max(start_ms + 40, end_ms)
        if media_end:
            # build_cue keeps every line visible for at least 200 ms.
            start_ms = min(start_ms, max(0, media_end - 200))
            end_ms = min(media_end, max(start_ms + 40, end_ms))
        bounds.append({"text": str(item.get("text") or ""), "start_ms": start_ms, "end_ms": end_ms, "from_asr": from_asr})
    return bounds


def _prefer_asr_clock(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    envelope: list[float] | None,
    hop_ms: int,
    duration_ms: int | None = None,
) -> list[dict[str, Any]] | None:
    """Use Whisper's clock when it consistently disagrees with official LRC.

    Official LRC remains the default.  A high-coverage, internally consistent
    ASR match with a large global offset indicates a different edit/version;
    in that case keeping the official clock leaves every cue out of sync.
    """
    candidate = _align_lines_to_asr(
        lines, asr_words, language, envelope=envelope, hop_ms=hop_ms
    )
    if not candidate:
        return None
    kept = [
        item
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    if len(candidate) != len(kept):
        return None
    matched = [row for row in candidate if row.get("from_asr")]
    if len(matched) < 3 or len(matched) / len(candidate) < 0.55:
        return None
    offsets = [
        int(row["start_ms"]) - int(line["ms"])
        for row, line in zip(candidate, kept)
        if row.get("from_asr") and line.get("ms") is not None
    ]
    if len(offsets) < 3:
        return None
    first_lrc = int(kept[0].get("ms") or 0) if kept else 0
    first_asr = int(candidate[0].get("start_ms") or 0) if candidate else 0
    if duration_ms and duration_ms >= 120_000 and first_lrc >= 10_000 and first_asr < 3_000:
        return None
    center = median(offsets)
    if abs(center) < 5_000:
        return None
    spread = median([abs(value - center) for value in offsets])
    if spread > 4_000:
        return None
    return candidate
