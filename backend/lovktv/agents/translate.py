"""Chinese translations for foreign karaoke lines, in the lovjpn 5-row spirit.

Japanese already has kanji / kana / romaji from ja_lyrics. This pass adds:
- line `zh`: natural Simplified Chinese of the sung line
- unit `zh`: short gloss per word
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lovktv.agents.ja_lyrics import (
    agent_enabled,
    agent_model,
    complete_json,
    lyric_source_key,
)
from lovktv.pipeline.lyrics import tokenize

# Bump this whenever the semantic-translation instructions change.  Existing
# notes contain per-word glosses and must not silently survive a prompt change.
TRANSLATE_SCHEMA = "lovjpn-zh-v5"
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
{"lines":[{"source":"<exact original line>","zh":"<faithful, clear Simplified Chinese>","units":[{"sing":"<surface>","zh":"<short contextual gloss>"}]}]}

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
   words produced by normal English tokenization). Keep contractions and
   hyphenated words whole, and omit punctuation-only units. Never group
   multiple English words into one unit. For Japanese/other languages, units
   may be grouped at natural sung-word boundaries while keeping source
   coverage and order.
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
            return cached
    if not agent_enabled():
        raise RuntimeError("翻译 agent 未启用")
    collected: list[dict[str, Any]] = []
    unique: list[str] = []
    seen: set[str] = set()
    for line in texts:
        if line and line not in seen:
            unique.append(line)
            seen.add(line)
    lang = str(language or "").strip() or "unknown"
    for start in range(0, len(unique), chunk_size):
        chunk = unique[start : start + chunk_size]
        numbered = "\n".join(f"{index + 1}. {line}" for index, line in enumerate(chunk))
        user = (
            f"Song: {title} / {artist}\n"
            f"Language: {lang}\n"
            "Translate every line below. First understand the batch and its recurring imagery/voice; then make a faithful, clear translation of each line in context. Keep source exactly the same. The Chinese line matters more than literal per-word glosses. For English, units must be one-for-one with sung words; do not group words.\n\n"
            f"{numbered}"
        )
        payload = complete_json(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ]
        )
        collected.extend(list(payload["lines"]))
    result = {
        "schema": TRANSLATE_SCHEMA,
        "source_hash": digest,
        "model": agent_model(),
        "title": title,
        "artist": artist,
        "language": lang,
        "lines": collected,
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


def _surface_key(value: str, language: str) -> str:
    """Normalize a token/unit surface for tolerant English matching."""
    text = lyric_source_key(value).strip().lower()
    if language == "en":
        # Keep apostrophes/hyphens inside a word but ignore surrounding lyric
        # punctuation (``love,`` vs ``love``).
        text = text.replace("’", "'").replace("‐", "-").replace("‑", "-")
        return "".join(ch for ch in text if ch.isalnum() or ch in "'-")
    return text


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
        sing = str(unit.get("sing") or "").strip()
        gloss = str(unit.get("zh") or "").strip()
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
        line_zh = str(item.get("zh") or "").strip()
        if line_zh and (overwrite or not str(cue.get("zh") or "").strip()):
            cue["zh"] = line_zh
        units = [unit for unit in item.get("units") or [] if isinstance(unit, dict)]
        glosses = [str(unit.get("zh") or "").strip() for unit in units]
        tokens = list(cue.get("tokens") or [])
        if not tokens or not glosses:
            continue
        if str(timeline.get("language") or "").lower().startswith("en"):
            projected = _english_unit_map(tokens, units)
            for index, token in enumerate(tokens):
                if index in projected and (overwrite or not str(token.get("zh") or "").strip()):
                    token["zh"] = projected[index]
                elif not str(token.get("zh") or "").strip():
                    fallback = _EN_FUNCTION_GLOSSES.get(
                        _surface_key(str(token.get("text") or ""), "en")
                    )
                    if fallback:
                        token["zh"] = fallback
            continue
        missing = [token for token in tokens if not str(token.get("zh") or "").strip()]
        if not missing:
            continue
        if len(missing) == len(tokens) and len(glosses) == len(tokens):
            for token, gloss in zip(tokens, glosses):
                if gloss:
                    token["zh"] = gloss
            continue
        used: set[int] = set()
        for token in missing:
            sing = lyric_source_key(token.get("text") or "")
            gloss = ""
            for index, unit in enumerate(units):
                if index in used:
                    continue
                if lyric_source_key(unit.get("sing") or "") == sing and unit.get("zh"):
                    gloss = str(unit.get("zh")).strip()
                    used.add(index)
                    break
            if gloss:
                token["zh"] = gloss
    timeline["translation"] = "lovjpn-zh"
    timeline["translation_model"] = str(notes.get("model") or agent_model())
    return timeline
