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

TRANSLATE_SCHEMA = "lovjpn-zh-v1"
CHINESE_LANGS = {"zh", "zh-cn", "zh-hans", "zh-hant", "yue", "cmn", "chinese"}

SYSTEM = """You translate karaoke lyrics for Chinese singers.
Return JSON only:
{"lines":[{"source":"<exact original line>","zh":"<natural Simplified Chinese>","units":[{"sing":"<surface>","zh":"<short gloss>"}]}]}

Rules:
1. `source` must equal the input line exactly.
2. `zh` is one natural Chinese sentence/phrase for the whole sung line. Do not leave it empty. Do not explain. Do not add 括号备注.
3. `units` follow the sung words in order. `sing` is the surface from the line (Japanese kana/kanji, English word, etc). `zh` is a short gloss, usually 1–6 Chinese characters.
4. Particles / function words still get a gloss: の→的, に→在, を→把, は→是, the→这, a→一个.
5. Keep the same number of units as meaningful sung pieces. Do not invent extra words.
6. Already-Chinese lines: copy the line into `zh` and leave unit glosses empty.
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
            "Translate every line below. Keep source exactly the same.\n\n"
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


def apply_zh_translation(
    timeline: dict[str, Any], notes: dict[str, Any]
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
        if line_zh and not str(cue.get("zh") or "").strip():
            cue["zh"] = line_zh
        units = [unit for unit in item.get("units") or [] if isinstance(unit, dict)]
        glosses = [str(unit.get("zh") or "").strip() for unit in units]
        tokens = list(cue.get("tokens") or [])
        if not tokens or not glosses:
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
