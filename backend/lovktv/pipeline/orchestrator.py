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
        if timed_lines:
            bounds = _align_lines_official_clock(
                lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms
            )
            asr_clock = _prefer_asr_clock(lines, asr_words, lang, envelope, hop_ms)
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
            agent_count = _apply_agent_matches(
                bounds, lines, asr_words, agent_matches, lang
            )
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
                    "agent+whisper" if agent_count else ("whisper" if used_asr_clock or not timed_lines else "official")
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


def _prefer_asr_clock(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    envelope: list[float] | None,
    hop_ms: int,
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
    center = median(offsets)
    if abs(center) < 5_000:
        return None
    spread = median([abs(value - center) for value in offsets])
    if spread > 4_000:
        return None
    return candidate
