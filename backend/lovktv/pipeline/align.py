"""Public lyric alignment facade.

Implementation is split into focused audio, matching, bounds, energy and clock modules;
this module preserves the historical import/API surface.
"""

from __future__ import annotations

from pathlib import Path

from lovktv.pipeline.language import detect_language
from lovktv.pipeline.lyrics import (
    build_cue,
    drop_credit_lines,
    fold_ja_netease_kanji,
    prepare_lyric_lines,
    timeline_from_lrc,
    tokenize,
)
from lovktv.pipeline.constants import *
from lovktv.pipeline.audio import *
from lovktv.pipeline.matching import *
from lovktv.pipeline.matching import (
    _asr_window,
    _best_asr_window,
    _cjk_asr_token_spans,
    _edit_distance,
    _en_asr_token_spans,
    _en_word_eq,
    _finish_token_hits,
    _join_asr,
    _norm_word,
    _usable_asr_words,
    _WORD,
    _JA_LEAD_FILLER,
)
from lovktv.pipeline.bounds import *
from lovktv.pipeline.bounds import _append_bound, _fallback_line_bounds, _voice_covers
from lovktv.pipeline.energy import *
from lovktv.pipeline.energy import _finalize_line_bounds, _vocal_end_near
from lovktv.pipeline.clock import *

def align_lyrics(
    lines: list[dict[str, Any]],
    language: str | None = None,
    audio_path: Path | None = None,
    duration_ms: int | None = None,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
    asr_words: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return karaoke timeline anchored to voice when possible."""
    joined = "".join(str(item.get("text") or "") for item in lines)
    lang = detect_language(joined, language)
    lines = prepare_lyric_lines(lines, lang)
    timed = [item for item in lines if item.get("ms") is not None]
    plain = [str(item.get("text") or "") for item in lines if item.get("ms") is None]

    if envelope is None and audio_path is not None:
        envelope, hop_ms = extract_envelope(audio_path, hop_ms)
        duration_ms = duration_ms or probe_duration_ms(audio_path)

    if not lines:
        return {
            "language": lang,
            "alignment": "empty",
            "alignment_source": "",
            "cues": [],
        }

    if asr_words:
        timed_lines = [item for item in lines if item.get("ms") is not None]
        if timed_lines:
            bounds = align_lines_official_clock(
                lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms
            )
        else:
            from lovktv.pipeline.lyric_anchor import align_lines_with_anchor, merge_whisper_and_anchor

            whisper_bounds = align_lines_to_asr(lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms)
            if not whisper_bounds:
                bounds = []
            else:
                bounds = merge_with_energy(
                    merge_whisper_and_anchor(
                        whisper_bounds,
                        align_lines_with_anchor(lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms),
                    ),
                    envelope,
                    hop_ms,
                )
        if bounds:
            cues = []
            for row in bounds:
                pieces = tokenize(str(row["text"]), lang)
                spans = asr_token_spans(pieces, row["start_ms"], row["end_ms"], asr_words, lang)
                if not spans:
                    spans = energy_token_spans(row["start_ms"], row["end_ms"], len(pieces), envelope or [], hop_ms)
                cue = build_cue(str(row["text"]), row["start_ms"], row["end_ms"], lang, spans)
                if cue:
                    cues.append(cue)
            return {
                "language": lang,
                "alignment": "lrc" if timed_lines else "asr",
                "alignment_source": "official" if timed_lines else "whisper",
                "cues": cues,
            }

    if envelope:
        regions = vocal_regions(envelope, hop_ms)
        phrases = vocal_phrases(regions)
        if plain and not timed:
            duration = duration_ms or 60_000
            work = assign_plain_lines(plain, phrases or regions, duration)
        elif timed:
            shift = estimate_lrc_offset(timed, phrases)
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
            spans = energy_token_spans(row["start_ms"], row["end_ms"], len(pieces), envelope, hop_ms)
            cue = build_cue(str(row["text"]), row["start_ms"], row["end_ms"], lang, spans)
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
    assigned = assign_plain_lines(texts, [], duration)
    timeline = timeline_from_lrc(assigned, lang, duration_ms=duration)
    timeline["alignment"] = "duration-fallback"
    timeline["alignment_source"] = ""
    return timeline
