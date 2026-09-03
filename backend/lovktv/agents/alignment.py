"""Agent-generated sung lyrics: ASR decides what was sung, the reference LRC
fixes spelling and fills gaps.

The model returns the lines actually sung, in transcript order, each anchored
to an ASR word span.  Reference lyrics may be a different version of the
song (film cut vs. studio single), so the model is free to drop reference
lines the recording omits and to write out sung parts the reference lacks.
Milliseconds are never taken from the model: the orchestrator derives them
from the ASR words the span points at.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from lovktv.agents.ja_lyrics import (
    agent_api_key,
    agent_base_url,
    agent_model,
)
from lovktv.domain.alignment import SUNG_SCHEMA, SungLyrics, parse_sung_lyrics
from lovktv.pipeline.lyrics import drop_credit_lines
from lovktv.pipeline.matching import _usable_asr_words

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)
# Whole-song requests keep global context for repeated choruses; beyond this
# many words the gateway's completion limit is at risk, so split by time.
_WHOLE_SONG_WORDS = 700
_WINDOW_WORDS = 320
_WINDOW_SEARCH = 60

SYSTEM = """You write the karaoke lyrics for a recording from its ASR
transcript. The transcript is the record of what was actually sung; the
reference lyrics are a spelling and context aid and may be a different
version of the song (film cut, live edit, extended mix). Return JSON only:
{"schema":"lovktv-sung-lyrics-v1","language":"en","rows":[
 {"text":"From now on","status":"matched","from":12,"to":14,"ref":7,
  "translation":"从现在起","tokens":[{"surface":"From","translation":"从"},
  {"surface":"now","translation":"现在"},{"surface":"on","translation":"起"}]}]}

Rules:
1. Return the sung lines in transcript time order. One row is one karaoke
line; follow the reference line breaks whenever the sung words correspond to
a reference line, otherwise break at natural phrase boundaries.
2. `text` is what was sung, spelled correctly. When the sung words correspond
to a reference line (even if the ASR misheard some words) copy that reference
line exactly and set `ref` to its number. When the recording sings something
the reference does not contain (another version, extra verse, ensemble part,
ad-lib) write it out from the transcript in the song's language with proper
spelling and punctuation, and set `ref` to null.
3. `from`/`to` are 1-based inclusive ASR word numbers. Never reuse a word, and
spans must be ascending. A span covers all the words of that line, including
misheard ones.
4. Incomplete lines: when the ASR captured only part of a reference line that
was clearly sung, return the complete reference line with the span over the
captured words.
5. Missed lines: when the reference and the neighbouring matched lines make
it clear a line was sung but the transcript has no words for it (a line in the
middle of a verse whose surrounding lines matched in order, with a time gap
that fits), emit it in its position with `status`:"inferred", no `from`/`to`,
and a short `reason`. Do not invent sections the recording omits; a missing
chorus with no time gap is simply not sung.
6. Skip spoken dialogue, crowd noise, title/credit lines, and ASR
hallucinations such as a phrase looping many times. Reference lines that are
not sung in this recording must not appear.
7. `translation` is a faithful Simplified Chinese translation of the line
(empty string when the line is already Chinese). `tokens` cover the line in
order: one token per word for Latin-script text, one per word or meaningful
unit for CJK; each token has `surface` and a short contextual `translation`.
Japanese tokens also carry `reading` (kana) and `romaji`.
"""


@dataclass
class SungGeneration:
    """Validated model output plus the exact word list its spans index."""

    lyrics: SungLyrics
    words: list[dict[str, Any]] = field(default_factory=list)

    def rows(self) -> list[dict[str, Any]]:
        return [row.model_dump(mode="json", by_alias=True) for row in self.lyrics.rows]


def _json_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        data = json.loads(match.group(0)) if match else {}
    if not isinstance(data, dict):
        raise ValueError("歌词 agent 返回的不是 JSON 对象")
    return data


def _request_content(messages: list[dict[str, str]]) -> str:
    base = agent_base_url()
    key = agent_api_key()
    if not base or not key:
        raise RuntimeError("歌词 agent 未配置 LOVKTV_AGENT_URL/OPENAI_BASE_URL")
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
            raise RuntimeError(str(data.get("msg") or "歌词 agent 请求失败"))
        data = data["data"]
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text") or "" if isinstance(part, dict) else str(part)
            for part in content
        )
    if not content:
        raise RuntimeError("歌词 agent 没有返回内容")
    return str(content)


def agent_words(asr_words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The numbered word list the model sees; spans index into this list."""
    return [
        {
            "index": index,
            "text": str(item.get("text") or "").strip(),
            "start_ms": int(item.get("start_ms") or 0),
            "end_ms": int(item.get("end_ms") or item.get("start_ms") or 0),
        }
        for index, item in enumerate(
            (item for item in _usable_asr_words(asr_words) if str(item.get("text") or "").strip()),
            1,
        )
    ]


def _build_messages(
    reference: list[str],
    words: list[dict[str, Any]],
    language: str,
    *,
    window: tuple[int, int] | None = None,
    emitted: list[str] | None = None,
) -> list[dict[str, str]]:
    numbered_lines = "\n".join(f"{i}. {text}" for i, text in enumerate(reference, 1)) or "(none)"
    numbered_words = "\n".join(
        f"{word['index']}. [{word['start_ms']}-{word['end_ms']}] {word['text']}" for word in words
    )
    parts = [f"Language: {language}", f"Reference lyrics:\n{numbered_lines}"]
    if window is not None:
        parts.append(
            f"This request covers ASR words {window[0]}-{window[1]} of the song. "
            "Return only lines whose words lie in this range; the rest of the song "
            "is handled separately."
        )
        if emitted:
            parts.append(
                "Lines already returned for the preceding words (context only, do not repeat):\n"
                + "\n".join(emitted)
            )
    parts.append(f"ASR words:\n{numbered_words}")
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _windows(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split the transcript at the widest silence near each window boundary."""
    out: list[list[dict[str, Any]]] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + _WINDOW_WORDS)
        if end < len(words):
            lo = max(start + 1, end - _WINDOW_SEARCH)
            best = end
            best_gap = -1
            for i in range(lo, end + 1):
                gap = int(words[i]["start_ms"]) - int(words[i - 1]["end_ms"])
                if gap > best_gap:
                    best_gap, best = gap, i
            end = best
        out.append(words[start:end])
        start = end
    return out


def _generate_whole(reference: list[str], words: list[dict[str, Any]], language: str) -> SungLyrics:
    payload = _json_payload(_request_content(_build_messages(reference, words, language)))
    return parse_sung_lyrics(payload, word_count=len(words))


def _generate_windowed(reference: list[str], words: list[dict[str, Any]], language: str) -> SungLyrics:
    rows: list[dict[str, Any]] = []
    emitted: list[str] = []
    last_to = 0
    for window in _windows(words):
        lo, hi = int(window[0]["index"]), int(window[-1]["index"])
        payload = _json_payload(
            _request_content(
                _build_messages(reference, window, language, window=(lo, hi), emitted=emitted[-3:])
            )
        )
        for row in payload.get("rows") or []:
            if not isinstance(row, dict):
                continue
            span = (row.get("from"), row.get("to"))
            if isinstance(span[0], int) and isinstance(span[1], int):
                # Keep every window's words inside its own range and strictly
                # after the previous window's last accepted span.
                if not (lo <= span[0] <= span[1] <= hi) or span[0] <= last_to:
                    continue
                last_to = span[1]
            rows.append(row)
            if str(row.get("text") or "").strip():
                emitted.append(str(row["text"]).strip())
    return parse_sung_lyrics(
        {"schema": SUNG_SCHEMA, "language": language, "rows": rows}, word_count=len(words)
    )


def _complete_from_reference(lyrics: SungLyrics, reference: list[str]) -> SungLyrics:
    """Rows that point at a reference line always carry its full text.

    The ASR often hears only part of a line; the model is asked to return the
    complete reference line, and this makes that guarantee unconditional.
    """
    for row in lyrics.rows:
        if row.ref is not None and 1 <= row.ref <= len(reference):
            row.text = reference[row.ref - 1]
    return lyrics


def generate_sung_lyrics(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    *,
    cache_path: Path | None = None,
) -> SungGeneration | None:
    """Return the sung lines for this recording, or None when the agent is
    unavailable or its answer fails validation (callers then fall back to the
    deterministic aligner)."""
    if not agent_base_url() or not agent_api_key() or not asr_words:
        return None
    reference = [
        str(item.get("text") or "").strip()
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    words = agent_words(asr_words)
    if not words:
        return None
    digest = hashlib.sha256(
        json.dumps(
            {"schema": SUNG_SCHEMA, "language": language, "reference": reference, "words": words},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("schema") == SUNG_SCHEMA and cached.get("source_hash") == digest:
                return SungGeneration(parse_sung_lyrics(cached, word_count=len(words)), words)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    lyrics: SungLyrics | None = None
    if len(words) <= _WHOLE_SONG_WORDS:
        try:
            lyrics = _generate_whole(reference, words, language)
        except Exception:
            lyrics = None
    if lyrics is None:
        try:
            lyrics = _generate_windowed(reference, words, language)
        except Exception:
            return None
    lyrics = _complete_from_reference(lyrics, reference)
    if cache_path:
        try:
            cache_path.write_text(
                json.dumps(
                    {
                        **lyrics.model_dump(mode="json", by_alias=True),
                        "schema": SUNG_SCHEMA,
                        "source_hash": digest,
                        "model": agent_model(),
                        "word_count": len(words),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
    return SungGeneration(lyrics, words)
