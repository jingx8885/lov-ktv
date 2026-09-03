"""Orchestrate the lyric-alignment pipeline components.

Preferred path: the agent has already decided *what* was sung (see
``lovktv.agents.alignment``); this module only turns its ASR word spans into
cue timing.  Without an agent answer the deterministic aligners place the
reference lyrics on the official LRC clock or on ASR words directly.
"""

from __future__ import annotations

from pathlib import Path
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
from lovktv.pipeline.bounds import hold_lines_until_next as _hold_lines_until_next
from lovktv.pipeline.clock import (
    align_lines_official_clock as _align_lines_official_clock,
)
from lovktv.pipeline.constants import HOP_MS
from lovktv.pipeline.energy import _finalize_line_bounds
from lovktv.pipeline.energy import merge_with_energy as _merge_with_energy
from lovktv.pipeline.language import detect_language
from lovktv.pipeline.lyrics import (
    build_cue,
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

# Extra display time granted per lyric token the ASR did not hear, so a line
# the model completed from the reference is not cut off after its last heard
# word.  Bounded by the next line's start.
_MISSING_TOKEN_MS = 350
# Nominal length of a line the ASR missed entirely when no neighbour bounds
# it on one side.
_INFERRED_LINE_MS = 3000
# Shortest slot an inferred line may be squeezed into when neighbours are tight.
_INFERRED_MIN_MS = 800
_MIN_LINE_MS = 200


def resolve_sung_rows(
    rows: list[dict[str, Any]],
    words: list[dict[str, Any]],
    language: str,
    duration_ms: int | None = None,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Give every agent row ``start_ms``/``end_ms`` derived from ASR words.

    ``matched`` rows take the span of the words they point at.  ``inferred``
    rows (sung, but absent from the transcript) are always shown: they share
    the silence between their matched neighbours weighted by text length, and
    borrow time from the previous line when there is no silence.
    """
    by_index = {int(word.get("index") or i): word for i, word in enumerate(words, 1)}
    placed: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["text"] = str(item.get("text") or "").strip()
        if not item["text"]:
            continue
        start = item.get("from")
        end = item.get("to")
        if start is not None and end is not None and int(start) in by_index and int(end) in by_index:
            item["status"] = "matched"
            item["start_ms"] = int(by_index[int(start)]["start_ms"])
            item["end_ms"] = max(item["start_ms"] + _MIN_LINE_MS, int(by_index[int(end)]["end_ms"]))
            item["heard"] = int(end) - int(start) + 1
        else:
            item["status"] = "inferred"
            item.pop("from", None)
            item.pop("to", None)
        placed.append(item)

    # Complete lines the ASR only partly heard: extend towards the next line.
    matched = [item for item in placed if item["status"] == "matched"]
    for index, item in enumerate(matched):
        missing = len(tokenize(item["text"], language)) - int(item.get("heard") or 0)
        if missing <= 0:
            continue
        limit = int(matched[index + 1]["start_ms"]) - 80 if index + 1 < len(matched) else None
        if duration_ms:
            limit = min(limit, int(duration_ms)) if limit is not None else int(duration_ms)
        wanted = item["end_ms"] + missing * _MISSING_TOKEN_MS
        item["end_ms"] = max(item["end_ms"], min(wanted, limit) if limit is not None else wanted)

    # Place inferred runs inside the gap between their matched neighbours.
    # An agent can infer a reference chorus from line order even when the
    # recording contains an instrumental break.  When an envelope is
    # available, require meaningful vocal energy in the interior of the gap;
    # otherwise dropping the inferred run is safer than displaying lyrics
    # over silence.  Keep the old behaviour when no audio envelope is known
    # (callers/tests may only have ASR word timestamps).
    vocal_regions = _vocal_regions(envelope, hop_ms) if envelope else []

    def has_vocal_interior(start_ms: int, end_ms: int) -> bool:
        if not vocal_regions:
            return False
        # Ignore short boundary bleed from the neighbouring matched lines.
        left = start_ms + 300
        right = end_ms - 300
        if right <= left:
            return False
        return any(
            min(region_end, right) - max(region_start, left) >= 300
            for region_start, region_end in vocal_regions
        )

    out: list[dict[str, Any]] = []
    i = 0
    while i < len(placed):
        if placed[i]["status"] == "matched":
            out.append(placed[i])
            i += 1
            continue
        j = i
        while j < len(placed) and placed[j]["status"] == "inferred":
            j += 1
        run = placed[i:j]
        prev_end = int(out[-1]["end_ms"]) if out else None
        next_start = int(placed[j]["start_ms"]) if j < len(placed) else None
        if prev_end is None and next_start is None:
            i = j
            continue
        if prev_end is None:
            prev_end = max(0, next_start - _INFERRED_LINE_MS * len(run))  # type: ignore[operator]
        if next_start is None:
            next_start = prev_end + _INFERRED_LINE_MS * len(run)
            if duration_ms:
                next_start = min(next_start, int(duration_ms))
        if envelope and not has_vocal_interior(prev_end, next_start):
            # No sung energy between the anchors: these are reference-only
            # guesses, not lines that should appear in the karaoke timeline.
            i = j
            continue
        needed = _INFERRED_MIN_MS * len(run)
        if next_start - prev_end < needed and out:
            # Not enough silence: borrow display time from the previous line
            # rather than dropping a line the model says was sung.
            prev_end = max(int(out[-1]["start_ms"]) + _MIN_LINE_MS, next_start - needed)
            out[-1]["end_ms"] = prev_end
        gap = max(next_start - prev_end, _MIN_LINE_MS * len(run))
        weights = [max(1, len(tokenize(item["text"], language))) for item in run]
        total = float(sum(weights))
        cursor = prev_end
        for item, weight in zip(run, weights):
            length = int(gap * weight / total)
            item["start_ms"] = cursor
            item["end_ms"] = cursor + max(_MIN_LINE_MS, length)
            cursor = item["end_ms"]
        run[-1]["end_ms"] = max(next_start, run[-1]["start_ms"] + _MIN_LINE_MS)
        out.extend(run)
        i = j
    for item in out:
        item.pop("heard", None)
    return _hold_lines_until_next(out)


def _overlay_agent_line(cue: dict[str, Any], row: dict[str, Any]) -> None:
    """Copy the agent's translation and token glosses onto a server-built cue.

    Token timing and boundaries stay server-owned; glosses are matched by
    position when the segmentation agrees, otherwise by surface text.
    """
    translation = str(row.get("translation") or "").strip()
    if translation:
        cue["translation"] = cue["zh"] = translation
    agent_tokens = [
        token for token in (row.get("tokens") or [])
        if isinstance(token, dict) and str(token.get("surface") or token.get("text") or "").strip()
    ]
    cue_tokens = cue.get("tokens") or []
    if not agent_tokens or not cue_tokens:
        return

    def _surface(token: dict[str, Any]) -> str:
        return str(token.get("surface") or token.get("text") or "").strip().casefold()

    if len(agent_tokens) == len(cue_tokens):
        pairs = list(zip(cue_tokens, agent_tokens))
    else:
        pairs = []
        cursor = 0
        for token in agent_tokens:
            wanted = _surface(token)
            hit = next((k for k in range(cursor, len(cue_tokens)) if _surface(cue_tokens[k]) == wanted), None)
            if hit is None:
                continue
            pairs.append((cue_tokens[hit], token))
            cursor = hit + 1
    for target, token in pairs:
        gloss = str(token.get("translation") or token.get("zh") or "").strip()
        if gloss:
            target["translation"] = target["zh"] = gloss
        for key in ("reading", "romaji"):
            value = str(token.get(key) or "").strip()
            if value:
                target[key] = value
        if isinstance(token.get("pronunciation"), dict) and token["pronunciation"]:
            target["pronunciation"] = token["pronunciation"]


def _cues_from_bounds(
    bounds: list[dict[str, Any]],
    language: str,
    asr_words: list[dict[str, Any]] | None,
    envelope: list[float] | None,
    hop_ms: int,
) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for row in bounds:
        text = str(row["text"])
        start_ms, end_ms = int(row["start_ms"]), int(row["end_ms"])
        pieces = tokenize(text, language)
        spans = _asr_token_spans(pieces, start_ms, end_ms, asr_words, language) if asr_words else None
        if not spans:
            spans = _energy_token_spans(start_ms, end_ms, len(pieces), envelope or [], hop_ms)
        cue = build_cue(text, start_ms, end_ms, language, spans)
        if cue:
            _overlay_agent_line(cue, row)
            cues.append(cue)
    return cues


def align_lyrics(
    lines: list[dict[str, Any]],
    language: str | None = None,
    audio_path: Path | None = None,
    duration_ms: int | None = None,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
    asr_words: list[dict[str, Any]] | None = None,
    sung_rows: list[dict[str, Any]] | None = None,
    sung_words: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a karaoke timeline.

    ``sung_rows``/``sung_words`` are the agent's answer (what was sung, with
    ASR word spans).  When present they define the lyric text; ``lines`` is
    only the reference used by the deterministic fallbacks.
    """
    joined = "".join(str(item.get("text") or "") for item in lines)
    lang = detect_language(joined, language)
    lines = prepare_lyric_lines(lines, lang)
    timed = [item for item in lines if item.get("ms") is not None]
    plain = [str(item.get("text") or "") for item in lines if item.get("ms") is None]

    if envelope is None and audio_path is not None:
        envelope, hop_ms = _extract_envelope(audio_path, hop_ms)
        duration_ms = duration_ms or _probe_duration_ms(audio_path)

    if sung_rows and sung_words:
        bounds = resolve_sung_rows(
            sung_rows,
            sung_words,
            lang,
            duration_ms,
            envelope=envelope,
            hop_ms=hop_ms,
        )
        cues = _cues_from_bounds(bounds, lang, asr_words, envelope, hop_ms)
        if cues:
            return {
                "language": lang,
                "alignment": "agent",
                "alignment_source": "agent+asr",
                "generation_source": "agent",
                "cues": cues,
            }

    if not lines:
        return {
            "language": lang,
            "alignment": "empty",
            "alignment_source": "",
            "cues": [],
        }

    if asr_words:
        if timed:
            bounds = _align_lines_official_clock(
                lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms
            )
        else:
            from lovktv.pipeline.lyric_anchor import (
                align_lines_with_anchor,
                merge_whisper_and_anchor,
            )

            whisper_bounds = _align_lines_to_asr(
                lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms
            )
            bounds = []
            if whisper_bounds:
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
            return {
                "language": lang,
                "alignment": "lrc" if timed else "asr",
                "alignment_source": "official" if timed else "whisper",
                "cues": _cues_from_bounds(bounds, lang, asr_words, envelope, hop_ms),
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
        return {
            "language": lang,
            "alignment": "onset",
            "alignment_source": str(audio_path.name) if audio_path else "envelope",
            "cues": _cues_from_bounds(bounds, lang, None, envelope, hop_ms),
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
