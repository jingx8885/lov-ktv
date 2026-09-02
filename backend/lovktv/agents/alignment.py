"""Agent-assisted matching of known lyrics to Whisper word timestamps.

The model chooses which ASR word span belongs to each lyric line.  It never
chooses milliseconds directly; the server derives those from the ASR words and
keeps the existing deterministic alignment as a fallback.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx

from lovktv.agents.ja_lyrics import (
    agent_api_key,
    agent_base_url,
    agent_model,
)
from lovktv.pipeline.lyrics import drop_credit_lines
from lovktv.pipeline.matching import _usable_asr_words

# v2 tightens repeated-line handling; old sparse matches are regenerated.
ALIGN_SCHEMA = "lovktv-align-v3"
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)

SYSTEM = """You match known karaoke lyric lines to a Whisper word transcript.
Return JSON only: {\"matches\":[{\"lyric\":1,\"from\":3,\"to\":8}]}.

Rules:
1. `lyric` is the 1-based lyric line number, and `from`/`to` are 1-based ASR
   word numbers (inclusive).
2. Match the sung words, not an intro/title/credits line. Never reuse an ASR
   word for two lines. The media may be an edited music video whose verse and
   chorus order differs from the LRC; in that case lyric numbers may be
   non-monotonic. Return matches in ASR time order (ascending `from`).
3. Repeated lines must use the matching words at their actual occurrence in the
   transcript, including occurrences that appear before an earlier LRC line.
   Return every occurrence that is plausibly sung, including short repeated
   chorus tags. Use the LRC clock and nearby context to disambiguate identical
   text; do not skip a line merely because another line looks similar. When
   identical text occurs more than once, prefer the lyric occurrence whose
   neighboring lyric numbers and surrounding words continue the same section.
   Do not jump backward to an earlier duplicate after matching later lyric
   lines unless the transcript clearly sings that earlier section next.
4. Whisper may mis-hear CJK, kana, accents, or punctuation. Use nearby context,
   word order, and the original lyric to choose the best span.
5. Every ASR word includes an authoritative `[start_ms-end_ms]` timestamp. Use
   the numbered ASR spans (not the LRC clock) as the timing source; do not
   invent, average, or shift word times while choosing `from`/`to`.
6. Bracketed lyric times are the source LRC clock, not ground truth. Compare
   them with ASR times and correct obvious offsets or version drift.
7. Omit a lyric only when no plausible sung counterpart exists in the ASR
   transcript (for example, an actual cut or spoken-only line); never invent
   ASR indices. Do not return timestamps or rewritten lyric text.
"""


def _source_hash(lines: list[str], words: list[dict[str, Any]], language: str) -> str:
    payload = json.dumps(
        {"schema": ALIGN_SCHEMA, "language": language, "lines": lines, "words": words},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse(raw: str) -> list[dict[str, int]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        data = json.loads(match.group(0)) if match else {}
    rows = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("对齐 agent 返回的不是 matches JSON")
    out: list[dict[str, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            lyric = int(row.get("lyric"))
            start = int(row.get("from"))
            end = int(row.get("to"))
        except (TypeError, ValueError):
            continue
        out.append({"lyric": lyric, "from": start, "to": end})
    return out


def _complete(messages: list[dict[str, str]]) -> list[dict[str, int]]:
    base = agent_base_url()
    key = agent_api_key()
    if not base or not key:
        raise RuntimeError("对齐 agent 未配置 LOVKTV_AGENT_URL/OPENAI_BASE_URL")
    body = {"model": agent_model(), "temperature": 0.0, "messages": messages}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f"{base}/chat/completions", headers=headers, json=body)
    except Exception as exc:
        if "socksio" not in str(exc):
            raise
        with httpx.Client(timeout=180.0, trust_env=False) as client:
            response = client.post(f"{base}/chat/completions", headers=headers, json=body)
    response.raise_for_status()
    data = response.json()
    if (
        isinstance(data, dict)
        and data.get("choices") is None
        and isinstance(data.get("data"), dict)
    ):
        if data.get("code") not in (None, 0, 200):
            raise RuntimeError(str(data.get("msg") or "对齐 agent 请求失败"))
        data = data["data"]
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text") or "" if isinstance(part, dict) else str(part)
            for part in content
        )
    if not content:
        raise RuntimeError("对齐 agent 没有返回内容")
    return _parse(str(content))


def align_lines_with_agent(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    *,
    cache_path: Path | None = None,
) -> list[dict[str, int]]:
    """Return validated lyric→ASR word spans, or an empty list on failure."""
    if not agent_base_url() or not agent_api_key() or not asr_words:
        return []
    kept = [
        item
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    words = [
        {
            "text": str(item.get("text") or ""),
            "start_ms": int(item.get("start_ms") or 0),
            "end_ms": int(item.get("end_ms") or item.get("start_ms") or 0),
        }
        for item in _usable_asr_words(asr_words)
        if str(item.get("text") or "").strip()
    ]
    if not kept or not words:
        return []
    lines_text = [str(item.get("text") or "") for item in kept]
    line_specs = []
    for item, text in zip(kept, lines_text):
        start = item.get("ms")
        end = item.get("end_ms")
        clock = (
            f"[{int(start)}-{int(end) if end is not None else '?'}] "
            if start is not None
            else "[no timestamp] "
        )
        line_specs.append(clock + text)
    digest = _source_hash(line_specs, words, language)
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("schema") == ALIGN_SCHEMA and cached.get("source_hash") == digest:
                return _validate(cached.get("matches") or [], len(kept), len(words))
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    # Keep prompts bounded while retaining the complete song in normal cases.
    words = words[:800]
    numbered_lines = "\n".join(f"{i}. {spec}" for i, spec in enumerate(line_specs, 1))
    numbered_words = "\n".join(
        f"{i}. [{word['start_ms']}-{word['end_ms']}] {word['text']}"
        for i, word in enumerate(words, 1)
    )
    try:
        matches = _complete(
            [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Language: {language}\nKnown lyric lines:\n{numbered_lines}\n\n"
                        f"Whisper ASR words:\n{numbered_words}"
                    ),
                },
            ]
        )
        valid = _validate(matches, len(kept), len(words))
    except Exception:
        return []
    if cache_path:
        try:
            cache_path.write_text(
                json.dumps(
                    {"schema": ALIGN_SCHEMA, "source_hash": digest, "matches": valid},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
    return valid


def _validate(rows: Any, lyric_count: int, word_count: int) -> list[dict[str, int]]:
    seen_lyrics: set[int] = set()
    used_words: set[int] = set()
    valid: list[dict[str, int]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            lyric, start, end = int(row["lyric"]), int(row["from"]), int(row["to"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (1 <= lyric <= lyric_count and 1 <= start <= end <= word_count):
            continue
        if lyric in seen_lyrics or any(index in used_words for index in range(start, end + 1)):
            continue
        seen_lyrics.add(lyric)
        used_words.update(range(start, end + 1))
        valid.append({"lyric": lyric, "from": start, "to": end})
    # The orchestrator builds the timeline in media order. Sorting here also
    # makes validation deterministic when the model returns valid rows in a
    # different order.
    return sorted(valid, key=lambda row: (row["from"], row["to"], row["lyric"]))
