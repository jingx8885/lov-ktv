"""Chinese translations for foreign karaoke lines, in the lovjpn 5-row spirit.

Japanese already has kanji / kana / romaji from ja_lyrics. This pass adds:
- line `zh`: natural Simplified Chinese of the sung line
- unit `zh`: short gloss per word
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from lovktv.agents.ja_lyrics import (
    agent_enabled,
    agent_model,
    complete_json,
    has_han,
    lyric_source_key,
    valid_zh,
)
from lovktv.pipeline.lyrics import tokenize

# Bump this whenever the semantic-translation instructions change.  Existing
# notes contain per-word glosses and must not silently survive a prompt change.
# Mixed Japanese/Chinese lines now require one gloss per embedded English
# word. Bump the cache schema so existing grouped notes are regenerated.
TRANSLATE_SCHEMA = "lovjpn-zh-v6"
CHINESE_LANGS = {"zh", "zh-cn", "zh-hans", "zh-hant", "yue", "cmn", "chinese"}

SYSTEM = """You translate karaoke lyrics for Chinese singers. Aim for a faithful,
literal-first Chinese translation that is easy to understand. Read the whole
batch as context and use the song title, artist, surrounding lines, grammar,
tense, tone, and imagery to resolve each line. Keep the original meaning and
structure whenever Chinese permits; make only the smallest adjustment needed
when a literal rendering would be ungrammatical, ambiguous, or misleading. Do
not beautify, paraphrase freely, or add information. The line translation is
the source of truth; word glosses explain how words contribute to that line.
Return JSON only:
{"lines":[{"source":"<exact original line>","translation":"<faithful, clear Simplified Chinese>","units":[{"surface":"<surface>","translation":"<short contextual gloss>"}]}]}

Field names: `translation` on a line (also called `zh`) is the Chinese line;
`surface` on a unit (also called `sing`) is the sung piece; `translation` on a
unit (also called `zh`) is its Chinese gloss. Every `translation` value must be
written in Chinese characters (简体中文). Never answer in English, never leave
the source language, and never copy a non-Chinese source line as its own
translation.

Rules:
1. `source` must equal the input line exactly.
2. `zh` is one faithful, clear Simplified Chinese sentence/phrase for the whole sung line. Preserve who does what to whom, negation, tense/aspect, modality, and emotional tone. Stay as close to the source wording as Chinese allows; do not freely paraphrase, explain, or add 括号备注.
3. `units` follow the sung pieces in order. `sing` is the surface from the line (Japanese kana/kanji, English word, etc.). A unit's `zh` is a concise *contextual contribution* to the line, normally 1–6 Chinese characters, not a dictionary definition.
4. When a Japanese source word/compound is written in Hanzi that is directly understandable in modern Chinese, prefer copying that same Hanzi into its unit `zh` (and retain it in the line translation), converting Japanese/traditional forms to Simplified Chinese as needed. For example, 電光石火 → 电光石火; do not rewrite it as “转瞬即逝”. Only change it when the Japanese and Chinese meanings differ or copying it would mislead (a Japanese false friend); then make the smallest context-appropriate correction.
5. Resolve remaining polysemy from context (for example, Japanese 君 may be “你” or “君”; English miss may be “想念” or “错过”). Prefer the closest sense that makes the whole line understandable and coherent with nearby lines. Do not preserve a dictionary/literal sense when it would change the lyric's meaning, but do not replace it with a freer poetic interpretation either.
6. Function words and particles are grammatical, not standalone vocabulary.
   For Japanese/other languages their `zh` may be empty when Chinese word
   order already expresses them. For English, however, every sung word unit
   must have a non-empty, concise contextual Chinese gloss (including words
   like the/of/to); use the relation that fits this line rather than leaving a
   blank. Do not force units for punctuation.
7. For English lines, return exactly one unit for every sung word (the same
   words produced by normal English tokenization). The same one-unit-per-word
   rule applies to every contiguous English run inside a Japanese, Chinese,
   or Cantonese line (for example, ``Give a reason`` becomes three units).
   Keep contractions and hyphenated words whole, and omit punctuation-only
   units. Never group multiple English words into one unit. Japanese/other
   native-language pieces may still be grouped at natural sung-word
   boundaries while keeping source coverage and order.
8. Already-Chinese lines: copy the line into `zh` and leave unit glosses empty.
9. Return every requested line, including repeated lines. Keep each `source` exact.
10. Before returning, compare every unit gloss with the completed `zh` line. Remove or revise any gloss that is a literal dictionary substitute but does not express that unit's role in this line.
"""


def is_chinese_lang(language: str | None) -> bool:
    return str(language or "").strip().lower() in CHINESE_LANGS


def _source_hash(lines: list[str], title: str, artist: str) -> str:
    payload = json.dumps(
        {"schema": TRANSLATE_SCHEMA, "title": title, "artist": artist, "lines": lines},
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_TRANSLATABLE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_NOT_CHINESE_NOTE = (
    "IMPORTANT: your previous answer for these lines was not Chinese (it was "
    "English, romaji, or a copy of the source). Every `translation` must be "
    "written in Simplified Chinese characters. Translate them again."
)
# A translation response is used to build the persisted lyric timeline.  Do
# not silently keep an incomplete/English response: retry the missing lines a
# few times and fail the batch explicitly if the agent never produces a valid
# answer.  The delay is configurable so deployments can tune rate-limit
# behaviour without changing code (and tests can set it to zero).
_TRANSLATION_MAX_ATTEMPTS = 3
_TRANSLATION_RETRY_DELAY = 0.25


def _retry_delay(attempt: int) -> None:
    """Wait briefly between agent retries, unless disabled by configuration."""
    raw = os.environ.get("LOVKTV_TRANSLATION_RETRY_DELAY")
    try:
        delay = float(raw) if raw is not None else _TRANSLATION_RETRY_DELAY
    except (TypeError, ValueError):
        delay = _TRANSLATION_RETRY_DELAY
    if delay > 0:
        time.sleep(delay * max(1, attempt))


def line_needs_zh(source: str) -> bool:
    """A lyric line that carries words (Latin, kana, or Han) must get Chinese."""
    return bool(_TRANSLATABLE.search(str(source or "")))


def translation_is_invalid(item: dict[str, Any]) -> bool:
    """True when the agent did not answer this line in Chinese."""
    source = str(item.get("source") or "")
    if not line_needs_zh(source):
        return False
    return not has_han(item.get("translation") or item.get("zh") or "")


def _request_translation(
    chunk: list[str], title: str, artist: str, lang: str, note: str = ""
) -> list[dict[str, Any]]:
    numbered = "\n".join(f"{index + 1}. {line}" for index, line in enumerate(chunk))
    user = (
        f"Song: {title} / {artist}\n"
        f"Language: {lang}\n"
        "Translate every line below. First understand the batch and its recurring imagery/voice; then make a faithful, clear translation of each line in context. Keep source exactly the same. The Chinese line matters more than literal per-word glosses. Units must follow words; every contiguous English run, including one embedded in a mixed-language line, is one unit per word. Do not group English words.\n"
        + (f"{note}\n" if note else "")
        + f"\n{numbered}"
    )
    payload = complete_json(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ]
    )
    return list(payload["lines"])


def _translate_chunk(
    chunk: list[str], title: str, artist: str, lang: str, note: str = ""
) -> list[dict[str, Any]]:
    """Translate one batch, retrying errors and unusable/missing lines.

    The agent may return only part of a batch or echo a source line in place
    of Chinese.  Those lines become the next retry batch.  Once the attempt
    budget is exhausted we raise instead of returning a partial result that
    would be persisted as a successful translation.
    """
    requested = [lyric_source_key(line) for line in chunk]
    pending = list(chunk)
    merged: dict[str, dict[str, Any]] = {}
    invalid_answer = bool(note)
    last_error: Exception | None = None

    for attempt in range(1, _TRANSLATION_MAX_ATTEMPTS + 1):
        note = _NOT_CHINESE_NOTE if invalid_answer else ""
        try:
            items = _request_translation(pending, title, artist, lang, note)
        except Exception as exc:  # noqa: BLE001 - retry the agent boundary
            last_error = exc
            if attempt >= _TRANSLATION_MAX_ATTEMPTS:
                raise
            _retry_delay(attempt)
            continue
        # A successful response supersedes any earlier transient transport
        # error; if this response is still invalid, report that fact instead.
        last_error = None

        # Keep only requested sources.  A source-less or unrelated model line
        # must not make the batch appear complete.
        for item in items:
            if not isinstance(item, dict):
                continue
            key = lyric_source_key(item.get("source") or "")
            if key in requested:
                merged[key] = item

        pending = [
            line
            for line in chunk
            if (item := merged.get(lyric_source_key(line))) is None
            or translation_is_invalid(item)
        ]
        if not pending:
            return [merged[key] for key in requested]

        invalid_answer = True
        if attempt < _TRANSLATION_MAX_ATTEMPTS:
            _retry_delay(attempt)

    # The loop either returned a complete result or raised the last transport
    # error.  This guard documents the invariant and protects future edits.
    if last_error is not None:
        raise last_error
    missing = ", ".join(lyric_source_key(line) for line in pending)
    raise RuntimeError(f"翻译 agent 重试后仍未返回有效中文：{missing}")


def _unique_lines(texts: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for line in texts:
        if line and line not in seen:
            unique.append(line)
            seen.add(line)
    return unique


def _write_cache(cache_path: Path | None, result: dict[str, Any]) -> None:
    if not cache_path:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def repair_notes(
    notes: dict[str, Any],
    title: str = "",
    artist: str = "",
    language: str = "",
    chunk_size: int = 24,
) -> int:
    """Re-translate every cached line that is not Chinese. Returns fixed count."""
    lang = str(language or notes.get("language") or "").strip() or "unknown"
    bad = _unique_lines(
        [
            lyric_source_key(item.get("source") or "")
            for item in notes.get("lines") or []
            if isinstance(item, dict) and translation_is_invalid(item)
        ]
    )
    if not bad:
        return 0
    if not agent_enabled():
        raise RuntimeError("翻译 agent 未启用")
    repaired: dict[str, dict[str, Any]] = {}
    for start in range(0, len(bad), chunk_size):
        repaired_items = _translate_chunk(
            bad[start : start + chunk_size],
            title,
            artist,
            lang,
            _NOT_CHINESE_NOTE,
        )
        for item in repaired_items:
            repaired[lyric_source_key(item.get("source") or "")] = item
    fixed = 0
    lines = notes.get("lines") or []
    for index, item in enumerate(lines):
        if not isinstance(item, dict) or not translation_is_invalid(item):
            continue
        replacement = repaired.get(lyric_source_key(item.get("source") or ""))
        if replacement:
            lines[index] = replacement
            fixed += 1
    return fixed


def translate_lines(
    lines: list[str],
    title: str = "",
    artist: str = "",
    language: str = "",
    cache_path: Path | None = None,
    chunk_size: int = 24,
    force: bool = False,
) -> dict[str, Any]:
    texts = [str(line or "") for line in lines]
    digest = _source_hash(texts, title, artist)
    if cache_path and cache_path.exists() and not force:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = {}
        if (
            cached.get("source_hash") == digest
            and cached.get("schema") == TRANSLATE_SCHEMA
            and cached.get("lines")
        ):
            # An old cache may hold English answers; re-ask only those lines
            # instead of throwing away the whole song.
            if repair_notes(cached, title, artist, language, chunk_size):
                _write_cache(cache_path, cached)
            return cached
    if not agent_enabled():
        raise RuntimeError("翻译 agent 未启用")
    collected: list[dict[str, Any]] = []
    unique = _unique_lines(texts)
    lang = str(language or "").strip() or "unknown"
    for start in range(0, len(unique), chunk_size):
        collected.extend(
            _translate_chunk(unique[start : start + chunk_size], title, artist, lang)
        )
    result = {
        "schema": TRANSLATE_SCHEMA,
        "source_hash": digest,
        "model": agent_model(),
        "title": title,
        "artist": artist,
        "language": lang,
        "lines": collected,
    }
    _write_cache(cache_path, result)
    return result


def _surface_key(value: str, language: str) -> str:
    """Normalize a token/unit surface for tolerant English matching."""
    text = lyric_source_key(value).strip().lower()
    if language == "en":
        # Keep apostrophes/hyphens inside a word but ignore surrounding lyric
        # punctuation (``love,`` vs ``love``).
        text = text.replace("’", "'").replace("‐", "-").replace("‑", "-")
        text = "".join(ch for ch in text if ch.isalnum() or ch in "'-")
        return text.strip("'")
    return text


def _unit_surface(unit: dict[str, Any]) -> str:
    return str(unit.get("surface") or unit.get("sing") or "").strip()


def _unit_translation(unit: dict[str, Any]) -> str:
    return valid_zh(unit.get("translation") or unit.get("zh") or "")


def _english_unit_map(
    tokens: list[dict[str, Any]], units: list[dict[str, Any]]
) -> dict[int, str]:
    """Project agent units onto timeline tokens, including grouped old notes.

    New prompts produce one unit per English word.  This tolerant projection
    keeps existing caches usable: a grouped unit is matched to its contiguous
    words and its contextual gloss is shown under each covered word when it
    cannot be safely split.
    """
    token_keys = [_surface_key(str(token.get("text") or ""), "en") for token in tokens]
    out: dict[int, str] = {}
    cursor = 0
    for unit in units:
        sing = _unit_surface(unit)
        gloss = _unit_translation(unit)
        if not sing:
            continue
        wanted = [
            _surface_key(piece, "en")
            for piece in tokenize(sing, "en")
            if _surface_key(piece, "en")
        ]
        if not wanted:
            continue
        found: int | None = None
        for start in range(cursor, len(tokens)):
            pos = start
            matched = True
            for key in wanted:
                while pos < len(tokens) and not token_keys[pos]:
                    pos += 1
                if pos >= len(tokens) or token_keys[pos] != key:
                    matched = False
                    break
                pos += 1
            if matched:
                found = start
                end = pos
                break
        if found is None:
            continue
        covered = [
            index
            for index in range(found, end)
            if token_keys[index]
        ]
        if not covered:
            continue
        # A correctly regenerated note has one gloss per word.  For an old
        # grouped note we cannot infer a faithful split, so repeat the
        # contextual phrase rather than leaving later words untranslated.
        if gloss:
            for index in covered:
                out[index] = gloss
        cursor = end
    return out


_EN_FUNCTION_GLOSSES = {
    "a": "一个",
    "an": "一个",
    "and": "和",
    "are": "是",
    "at": "在",
    "be": "是",
    "but": "但",
    "by": "被",
    "for": "为",
    "from": "从",
    "in": "在",
    "is": "是",
    "it's": "这是",
    "it": "它",
    "of": "的",
    "on": "在",
    "or": "或",
    "that": "那",
    "the": "这",
    "to": "到",
    "was": "是",
    "were": "是",
    "with": "和",
    "'cause": "因为",
    "’cause": "因为",
}


def apply_zh_translation(
    timeline: dict[str, Any], notes: dict[str, Any], *, overwrite: bool = False
) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    for item in notes.get("lines") or []:
        source = lyric_source_key(item.get("source") or "")
        if source:
            by_source[source] = item
    for cue in timeline.get("cues") or []:
        text = lyric_source_key(cue.get("text") or "")
        original = lyric_source_key(cue.get("source_text") or text)
        item = by_source.get(original) or by_source.get(text)
        if not item:
            continue
        line_zh = valid_zh(item.get("translation") or item.get("zh") or "")
        if line_zh and (overwrite or not valid_zh(cue.get("zh") or "")):
            cue["zh"] = line_zh
            cue["translation"] = line_zh
        units = [unit for unit in item.get("units") or [] if isinstance(unit, dict)]
        glosses = [_unit_translation(unit) for unit in units]
        tokens = list(cue.get("tokens") or [])
        if not tokens or not glosses:
            continue
        # English runs can occur inside Japanese/Chinese/Cantonese lines too.
        # Project them first, and allow a fresh per-word translation to replace
        # the Japanese annotator's old grouped gloss on the first word.  Keep
        # the legacy grouped-note fallback for non-English timelines: without
        # one gloss per source word there is no faithful way to split a phrase.
        language_key = str(timeline.get("language") or "").lower()
        english_units = [
            unit
            for unit in units
            if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", _unit_surface(unit))
        ]
        wordwise = all(
            len(tokenize(_unit_surface(unit), "en")) == 1
            for unit in english_units
        )
        projected = (
            _english_unit_map(tokens, units)
            if language_key.startswith("en") or wordwise
            else {}
        )
        for index, token in enumerate(tokens):
            if index not in projected:
                continue
            existing = valid_zh(token.get("zh") or "")
            is_latin = bool(
                re.match(
                    r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]", str(token.get("text") or "")
                )
            )
            if overwrite or not existing or is_latin:
                token["zh"] = projected[index]
                token["translation"] = projected[index]

        if language_key.startswith("en") or wordwise:
            for index, token in enumerate(tokens):
                token_text = str(token.get("text") or "")
                if (
                    index not in projected
                    and re.match(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]", token_text)
                    and not valid_zh(token.get("zh") or "")
                ):
                    fallback = _EN_FUNCTION_GLOSSES.get(
                        _surface_key(token_text, "en")
                    )
                    if fallback:
                        token["zh"] = fallback
                        token["translation"] = fallback
        if language_key.startswith("en"):
            continue
        missing = [token for token in tokens if not valid_zh(token.get("zh") or "")]
        if not missing:
            continue
        if len(missing) == len(tokens) and len(glosses) == len(tokens):
            for token, gloss in zip(tokens, glosses):
                if gloss:
                    token["zh"] = gloss
                    token["translation"] = gloss
            continue
        used: set[int] = set()
        for token in missing:
            sing = lyric_source_key(token.get("text") or "")
            gloss = ""
            for index, unit in enumerate(units):
                if index in used:
                    continue
                if lyric_source_key(_unit_surface(unit)) == sing and _unit_translation(unit):
                    gloss = _unit_translation(unit)
                    used.add(index)
                    break
            if gloss:
                token["zh"] = gloss
                token["translation"] = gloss
    timeline["translation"] = "lovjpn-zh"
    timeline["translation_model"] = str(notes.get("model") or agent_model())
    return timeline
