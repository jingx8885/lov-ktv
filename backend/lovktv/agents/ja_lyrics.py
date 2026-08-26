"""Japanese lyric annotation agent: kanji→hiragana, katakana→source language.

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

SYSTEM = """You are a Japanese karaoke lyric annotator.
Return JSON only:
{"lines":[{"source":"<exact original line>","units":[{"sing":"...","label":"..."}]}]}

Rules:
1. `source` must equal the input line exactly.
2. Units cover the whole line in order. Do not drop or invent words.
3. Kanji / kanji+okurigana: `sing` is the correct hiragana reading in THIS song; `label` is only the kanji (止, 君, 溢). Use lyric context (君 as you → きみ, not くん; 煌めき → きらめき).
4. Katakana loanwords (メモリー, コーヒー, ダンサー, カフェ): keep the katakana in `sing`; `label` is the original English/French/etc word (memory, coffee, dancer, café). Never write romaji like memorii or koohii.
5. Japanese katakana (ズレ, フリ, ダメ, ヤバ): keep katakana in `sing`; `label` is empty.
6. Hiragana, punctuation, numbers, already-Latin text: `sing` as written; `label` empty.
"""


def agent_base_url() -> str:
    raw = (os.environ.get("LOVKTV_AGENT_URL") or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
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


def _is_katakana(text: str) -> bool:
    body = [char for char in text if not char.isspace()]
    return bool(body) and all(_KATAKANA.match(char) or char in _KATA_MARK for char in body)


def _source_hash(lines: list[str], title: str, artist: str) -> str:
    payload = json.dumps({"title": title, "artist": artist, "lines": lines}, ensure_ascii=False)
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
            units.append({"sing": sing, "label": str(unit.get("label") or "").strip()})
        if source and units:
            cleaned.append({"source": source, "units": units})
    if not cleaned:
        raise ValueError("agent 没有可用的注音行")
    return {"lines": cleaned}


def complete_json(messages: list[dict[str, str]], model: str | None = None) -> dict[str, Any]:
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
    if isinstance(data, dict) and data.get("choices") is None and isinstance(data.get("data"), dict):
        if data.get("code") not in (None, 0, 200):
            raise RuntimeError(str(data.get("msg") or "agent 请求失败"))
        data = data["data"]
    message = ((data.get("choices") or [{}])[0].get("message") or {})
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text") or "" if isinstance(part, dict) else str(part) for part in content
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
) -> dict[str, Any]:
    texts = [str(line or "") for line in lines]
    digest = _source_hash(texts, title, artist)
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = {}
        if cached.get("source_hash") == digest and cached.get("lines"):
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
        collected.extend(_request_chunk(unique[start : start + chunk_size], title, artist))
    result = {
        "source_hash": digest,
        "model": agent_model(),
        "title": title,
        "artist": artist,
        "lines": collected,
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def lyric_source_key(text: str) -> str:
    """Agent often echoes '1. 原文'; match the lyric line without that prefix."""
    return _LINE_NO.sub("", unicodedata.normalize("NFKC", str(text or "")), count=1).strip()


def _clean_label(label: str) -> str:
    raw = unicodedata.normalize("NFKC", str(label or "")).strip()
    kanji = "".join(char for char in raw if _KANJI.match(char))
    if kanji:
        return kanji
    if re.search(r"[A-Za-zÀ-ÿ]", raw):
        return raw
    return ""


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
                return source[start : index + 1]
    return ""


def expand_units(units: list[dict[str, str]], source: str = "") -> list[tuple[str, str]]:
    from lovktv.pipeline.lyrics import ja_token_specs

    specs: list[tuple[str, str]] = []
    source = unicodedata.normalize("NFKC", source or "")
    for unit in units:
        sing = lyric_source_key(unit.get("sing") or "")
        raw_label = unicodedata.normalize("NFKC", unit.get("label") or "")
        label = _clean_label(raw_label)
        if not sing.strip() or _INDEX_UNIT.fullmatch(sing.strip()):
            continue
        if re.search(r"[A-Za-z]", sing) and not _KANJI.search(sing) and not _KANA.search(sing):
            parts = [part for part in _LATIN_PART.findall(sing) if part.strip()]
            for part in parts:
                specs.append((part, label if len(parts) == 1 else ""))
            continue
        kanji_only = "".join(char for char in raw_label if _KANJI.match(char))
        if len(kanji_only) >= 2:
            snippet = raw_label if re.search(r"[\u3040-\u309f]", raw_label) else _source_span_for_kanji(source, kanji_only)
            leftover = ja_token_specs(snippet or raw_label)
            if leftover:
                specs.extend(leftover)
                continue
        if _KANJI.search(sing):
            leftover = ja_token_specs(sing)
            for piece, fallback in leftover:
                specs.append((piece, label if label and fallback else (label or fallback)))
            continue
        surface = "".join(char for char in sing if not char.isspace())
        if label or _is_katakana(surface):
            specs.append((surface, label))
            continue
        for char in surface:
            specs.append((char, ""))
    return specs


def apply_ja_annotation(timeline: dict[str, Any], notes: dict[str, Any]) -> dict[str, Any]:
    by_source: dict[str, list[dict[str, str]]] = {}
    for item in notes.get("lines") or []:
        source = lyric_source_key(item.get("source") or "")
        units = [unit for unit in item.get("units") or [] if unit.get("sing")]
        if source and units:
            by_source[source] = units
    for cue in timeline.get("cues") or []:
        text = lyric_source_key(cue.get("text") or "")
        units = by_source.get(text)
        if not units:
            continue
        specs = expand_units(units, source=text)
        if not specs:
            continue
        start_ms = int(cue["start_ms"])
        end_ms = int(cue.get("sing_end_ms") or cue["end_ms"])
        span = max(end_ms - start_ms, 200)
        unit = span / len(specs)
        tokens = []
        cursor = start_ms
        for index, (piece, label) in enumerate(specs):
            token_end = end_ms if index == len(specs) - 1 else int(cursor + unit)
            tokens.append(
                {
                    "text": piece,
                    "start_ms": int(cursor),
                    "end_ms": int(max(cursor + 40, token_end)),
                    "reading": label,
                }
            )
            cursor = token_end
        tokens[-1]["end_ms"] = end_ms
        cue["tokens"] = tokens
    timeline["annotation"] = "ja-agent"
    timeline["annotation_model"] = str(notes.get("model") or agent_model())
    return timeline
