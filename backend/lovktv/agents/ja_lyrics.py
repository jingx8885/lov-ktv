"""Japanese lyric annotation agent: display kanji + hiragana above, katakana + English above.

This is not a word list. An LLM reads the whole lyric and returns units.
Results are cached per song so import/realign can reuse them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import httpx

_KATAKANA = re.compile(r"[\u30a0-\u30ff]")
_KANJI = re.compile(r"[\u3400-\u9fff\uf900-\ufaff々]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_KATA_MARK = set("ー・ヽヾ")
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)
_LINE_NO = re.compile(r"^\d+\.\s*")
_INDEX_UNIT = re.compile(r"^\d+\.$")
_LATIN_PART = re.compile(r"[A-Za-z0-9']+(?:[!?.,…]+)?|[^\sA-Za-z0-9']+")
_LATIN_WORD = re.compile(r"[A-Za-z]+")
_HIRA = re.compile(r"[\u3040-\u309f]")
ANNOTATION_SCHEMA = "restore-ja-v1"

SYSTEM = """You restore Japanese karaoke lyrics and annotate them.
Return JSON only:
{"lines":[{"source":"<exact original line>","units":[{"sing":"...","label":"...","romaji":"..."}]}]}

Rules:
1. `source` must equal the input line exactly, even when the input is romaji.
2. If the line is Hepburn romaji, restore Japanese in `sing` (ひらがな / カタカナ). Example: "itsumo no you ni" → いつもの / ように. Do not leave romaji in `sing`.
3. Units cover the WHOLE sung line in order. Do not drop or invent words. If the source is romaji, every source word must become a unit (me magurushii jikan no mure ga → めまぐるしい / じかん / の / むれ / が).
4. Kanji / kanji+okurigana: `sing` is the original writing as in the lyric (止まった, 君, 溢れる); `label` is the hiragana reading in THIS song (とまった, きみ, あふれる); `romaji` is Hepburn (tomatta, kimi). Split at word boundaries: 走り続ける → 走り / 続ける. Context: 君 as you → きみ, not くん.
5. Katakana loanwords (メモリー, コーヒー, ダンサー): `sing` is katakana; `label` is the original English/French word (memory, coffee, dancer); `romaji` is empty. Never write memorii or koohii.
6. Native katakana (ズレ, フリ, ダメ): `sing` katakana; `label` empty; `romaji` Hepburn (zure, furi).
7. Hiragana particles / leftover kana: `sing` as kana; `label` empty; `romaji` Hepburn (no, ni, you).
8. Already-English words in the lyric (Give a reason, Here we go): keep them in `sing`; `label` and `romaji` empty.
9. Every line MUST include `zh`: a natural Simplified Chinese translation of the whole sung line. No notes, no brackets.
10. Every unit MUST include `zh`: a short Chinese gloss (usually 1–6 characters). の→的, に→在, メモリー→记忆.
"""


def agent_base_url() -> str:
    raw = (
        os.environ.get("LOVKTV_AGENT_URL") or os.environ.get("OPENAI_BASE_URL") or ""
    ).rstrip("/")
    if not raw:
        return ""
    return raw if raw.endswith("/v1") else raw + "/v1"


def agent_api_key() -> str:
    return os.environ.get("LOVKTV_AGENT_KEY") or os.environ.get("OPENAI_API_KEY") or ""


def agent_model() -> str:
    return (
        os.environ.get("LOVKTV_AGENT_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-5.4-mini"
    )


def agent_enabled() -> bool:
    if os.environ.get("LOVKTV_JA_AGENT", "1") in {"0", "false", "no"}:
        return False
    return bool(agent_base_url() and agent_api_key())


def agent_status() -> dict[str, Any]:
    return {
        "enabled": agent_enabled(),
        "model": agent_model() if agent_enabled() else "",
    }


def line_is_romaji(text: str) -> bool:
    source = lyric_source_key(text)
    if _KANA.search(source) or _KANJI.search(source):
        return False
    letters = [char for char in source if char.isalpha()]
    return bool(letters) and all(char.isascii() for char in letters)


def japanese_from_units(units: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for unit in units:
        sing = lyric_source_key(unit.get("sing") or "")
        if not sing:
            continue
        if (
            parts
            and re.match(r"[A-Za-z0-9']", sing)
            and re.search(r"[A-Za-z0-9']$", parts[-1] or "")
        ):
            parts.append(" ")
        parts.append(sing)
    return "".join(parts)


def _is_katakana(text: str) -> bool:
    body = [char for char in text if not char.isspace()]
    return bool(body) and all(
        _KATAKANA.match(char) or char in _KATA_MARK for char in body
    )


def _source_hash(lines: list[str], title: str, artist: str) -> str:
    payload = json.dumps(
        {"schema": ANNOTATION_SCHEMA, "title": title, "artist": artist, "lines": lines},
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        data = json.loads(match.group(0)) if match else {}
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list):
        raise ValueError("agent 返回的不是 lines JSON")
    cleaned = []
    for item in lines:
        if not isinstance(item, dict):
            continue
        source = lyric_source_key(item.get("source") or "")
        units = []
        for unit in item.get("units") or []:
            if not isinstance(unit, dict):
                continue
            sing = lyric_source_key(str(unit.get("sing") or "").strip())
            if not sing or _INDEX_UNIT.fullmatch(sing):
                continue
            units.append(
                {
                    "sing": sing,
                    "label": str(unit.get("label") or "").strip(),
                    "romaji": str(unit.get("romaji") or "").strip(),
                    "zh": str(unit.get("zh") or "").strip(),
                }
            )
        line_zh = str(item.get("zh") or "").strip()
        if source and (units or line_zh):
            cleaned.append(
                {
                    "source": source,
                    "zh": line_zh,
                    "units": units,
                }
            )
    if not cleaned:
        raise ValueError("agent 没有可用的注音行")
    return {"lines": cleaned}


def complete_json(
    messages: list[dict[str, str]], model: str | None = None
) -> dict[str, Any]:
    base = agent_base_url()
    key = agent_api_key()
    if not base or not key:
        raise RuntimeError("日语注音 agent 未配置 LOVKTV_AGENT_URL/OPENAI_BASE_URL")
    body = {
        "model": model or agent_model(),
        "temperature": 0.1,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    url = f"{base}/chat/completions"
    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(url, headers=headers, json=body)
    except Exception as exc:
        if "socksio" not in str(exc):
            raise
        with httpx.Client(timeout=180.0, trust_env=False) as client:
            response = client.post(url, headers=headers, json=body)
    response.raise_for_status()
    data = response.json()
    if (
        isinstance(data, dict)
        and data.get("choices") is None
        and isinstance(data.get("data"), dict)
    ):
        if data.get("code") not in (None, 0, 200):
            raise RuntimeError(str(data.get("msg") or "agent 请求失败"))
        data = data["data"]
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text") or "" if isinstance(part, dict) else str(part)
            for part in content
        )
    if not content:
        raise RuntimeError(str(data.get("msg") or "agent 没有返回内容"))
    return _parse_payload(str(content))


def _request_chunk(lines: list[str], title: str, artist: str) -> list[dict[str, Any]]:
    numbered = "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))
    user = (
        f"Song: {title} / {artist}\n"
        "Annotate every line below. Keep source exactly the same.\n\n"
        f"{numbered}"
    )
    payload = complete_json(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ]
    )
    return list(payload["lines"])


def annotate_ja_lines(
    lines: list[str],
    title: str = "",
    artist: str = "",
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
            and cached.get("schema") == ANNOTATION_SCHEMA
            and cached.get("lines")
        ):
            return cached
    if not agent_enabled():
        raise RuntimeError("日语注音 agent 未启用")
    collected: list[dict[str, Any]] = []
    unique: list[str] = []
    seen: set[str] = set()
    for line in texts:
        if line and line not in seen:
            unique.append(line)
            seen.add(line)
    for start in range(0, len(unique), chunk_size):
        collected.extend(
            _request_chunk(unique[start : start + chunk_size], title, artist)
        )
    result = {
        "schema": ANNOTATION_SCHEMA,
        "source_hash": digest,
        "model": agent_model(),
        "title": title,
        "artist": artist,
        "lines": collected,
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


def lyric_source_key(text: str) -> str:
    """Agent often echoes '1. 原文'; match the lyric line without that prefix."""
    return _LINE_NO.sub(
        "", unicodedata.normalize("NFKC", str(text or "")), count=1
    ).strip()


def _clean_label(label: str) -> str:
    raw = unicodedata.normalize("NFKC", str(label or "")).strip()
    if not raw:
        return ""
    if (
        re.search(r"[A-Za-zÀ-ÿ]", raw)
        and not _KANJI.search(raw)
        and not _HIRA.search(raw)
    ):
        return raw
    hira = "".join(char for char in raw if _HIRA.match(char) or char == "ー")
    kanji = "".join(char for char in raw if _KANJI.match(char))
    if hira and not kanji:
        return hira
    if kanji:
        return kanji
    return ""


def _latin_label(label: str) -> str:
    raw = unicodedata.normalize("NFKC", str(label or "")).strip()
    return raw if re.search(r"[A-Za-zÀ-ÿ]", raw) and not _KANJI.search(raw) else ""


def _sung_kana(specs: list[tuple[str, str]]) -> str:
    bits: list[str] = []
    for piece, reading in specs:
        if reading and not _KANJI.search(reading):
            bits.append(reading)
        else:
            bits.append(piece)
    return _kana_key("".join(bits))


def _flip_kanji_specs(snippet: str, sing: str) -> list[tuple[str, str]] | None:
    from lovktv.pipeline.lyrics import ja_token_specs

    if not snippet:
        return None
    leftover = _merge_plain_kana(ja_token_specs(snippet))
    if leftover and _sung_kana(leftover) == _kana_key(sing):
        return leftover
    return None


def _join_surfaces(parts: list[str]) -> str:
    out: list[str] = []
    for piece in parts:
        if not piece:
            continue
        if (
            out
            and re.match(r"[A-Za-z0-9']", piece)
            and re.search(r"[A-Za-z0-9']$", out[-1] or "")
        ):
            out.append(" ")
        out.append(piece)
    return "".join(out)


def _source_span_for_kanji(source: str, kanji: str) -> str:
    """Slice of the original line covering these kanji, plus following okurigana."""
    if not source or not kanji:
        return ""
    start: int | None = None
    matched = 0
    for index, char in enumerate(source):
        if matched < len(kanji) and char == kanji[matched]:
            if start is None:
                start = index
            matched += 1
            if matched == len(kanji):
                end = index + 1
                while end < len(source) and _HIRA.match(source[end]):
                    end += 1
                return source[start:end]
    return ""


def _kana_key(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKC", text or "") if not char.isspace()
    )


def _merge_plain_kana(specs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for piece, label in specs:
        if (
            merged
            and not label
            and not merged[-1][1]
            and _KANA.search(piece)
            and not _KANJI.search(piece)
            and _KANA.search(merged[-1][0])
            and not _KANJI.search(merged[-1][0])
        ):
            merged[-1] = (merged[-1][0] + piece, "")
            continue
        merged.append((piece, label))
    return merged


def _units_cover_romaji(units: list[dict[str, str]], source: str) -> bool:
    words = _LATIN_WORD.findall(source)
    if len(words) < 3:
        return True
    covered: list[str] = []
    for unit in units:
        roma = str(unit.get("romaji") or "").strip()
        sing = lyric_source_key(unit.get("sing") or "")
        if roma:
            covered.extend(_LATIN_WORD.findall(roma))
        elif (
            _LATIN_WORD.search(sing)
            and not _KANA.search(sing)
            and not _KANJI.search(sing)
        ):
            covered.extend(_LATIN_WORD.findall(sing))
    return len(covered) >= max(2, int(len(words) * 0.7))


def expand_units(
    units: list[dict[str, str]], source: str = ""
) -> list[tuple[str, str]]:
    from lovktv.pipeline.lyrics import ja_token_specs

    specs: list[tuple[str, str]] = []
    source = unicodedata.normalize("NFKC", source or "")
    for unit in units:
        sing = lyric_source_key(unit.get("sing") or "")
        raw_label = unicodedata.normalize("NFKC", unit.get("label") or "")
        label = _clean_label(raw_label)
        if not sing.strip() or _INDEX_UNIT.fullmatch(sing.strip()):
            continue
        if (
            re.search(r"[A-Za-z]", sing)
            and not _KANJI.search(sing)
            and not _KANA.search(sing)
        ):
            parts = [part for part in _LATIN_PART.findall(sing) if part.strip()]
            english = _latin_label(label)
            for part in parts:
                specs.append((part, english if len(parts) == 1 else ""))
            continue
        surface = "".join(char for char in sing if not char.isspace())
        kanji_only = "".join(char for char in raw_label if _KANJI.match(char))
        if _KANJI.search(sing):
            leftover = _merge_plain_kana(ja_token_specs(sing))
            if leftover:
                if (
                    label
                    and _HIRA.search(label)
                    and not _KANJI.search(label)
                    and len(leftover) == 1
                ):
                    specs.append((leftover[0][0], label))
                else:
                    specs.extend(leftover)
                continue
        if kanji_only:
            snippet = (
                raw_label
                if _HIRA.search(raw_label)
                else _source_span_for_kanji(source, kanji_only)
            )
            flipped = _flip_kanji_specs(snippet, surface)
            if flipped:
                specs.extend(flipped)
                continue
            display = snippet or raw_label or kanji_only
            specs.append((display if _KANJI.search(display) else kanji_only, surface))
            continue
        if _is_katakana(surface):
            specs.append((surface, _latin_label(label)))
            continue
        if _latin_label(label) or str(unit.get("romaji") or "").strip():
            specs.append((surface, _latin_label(label)))
            continue
        for char in surface:
            specs.append((char, ""))
    return specs


def apply_ja_annotation(
    timeline: dict[str, Any], notes: dict[str, Any]
) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    for item in notes.get("lines") or []:
        source = lyric_source_key(item.get("source") or "")
        units = [unit for unit in item.get("units") or [] if unit.get("sing")]
        if source and units:
            by_source[source] = item
    for cue in timeline.get("cues") or []:
        text = lyric_source_key(cue.get("text") or "")
        original = lyric_source_key(cue.get("source_text") or text)
        item = by_source.get(original) or by_source.get(text)
        if not item:
            continue
        units = [unit for unit in item.get("units") or [] if unit.get("sing")]
        line_zh = str(item.get("zh") or "").strip()
        if line_zh:
            cue["zh"] = line_zh
        specs: list[tuple[str, str, str, str]] = []
        for unit in units:
            roma = str(unit.get("romaji") or "").strip()
            gloss = str(unit.get("zh") or "").strip()
            pieces = expand_units([unit], source=original)
            for index, (piece, label) in enumerate(pieces):
                specs.append(
                    (
                        piece,
                        label,
                        roma if index == 0 else "",
                        gloss if index == 0 else "",
                    )
                )
        if not specs:
            continue
        japanese = japanese_from_units(units)
        displayed = _join_surfaces([piece for piece, _label, _roma, _gloss in specs])
        current = lyric_source_key(cue.get("text") or "")
        if line_is_romaji(original) and not _units_cover_romaji(units, original):
            if line_is_romaji(current):
                continue
            if japanese and japanese == current:
                cue["text"] = original
                continue
        if (displayed or japanese) and line_is_romaji(original):
            cue["source_text"] = original
            cue["text"] = displayed or japanese
        start_ms = int(cue["start_ms"])
        end_ms = int(cue.get("sing_end_ms") or cue["end_ms"])
        span = max(end_ms - start_ms, 200)
        unit_ms = span / len(specs)
        tokens = []
        cursor = start_ms
        for index, (piece, label, roma, gloss) in enumerate(specs):
            token_end = end_ms if index == len(specs) - 1 else int(cursor + unit_ms)
            token = {
                "text": piece,
                "start_ms": int(cursor),
                "end_ms": int(max(cursor + 40, token_end)),
                "reading": label,
                "romaji": roma,
            }
            if gloss:
                token["zh"] = gloss
            tokens.append(token)
            cursor = token_end
        tokens[-1]["end_ms"] = end_ms
        cue["tokens"] = tokens
    timeline["annotation"] = "ja-agent"
    timeline["annotation_model"] = str(notes.get("model") or agent_model())
    return timeline
