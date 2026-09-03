"""Agent-assisted lyric alignment and direct lyric-result generation.

The preferred contract returns a complete row for every source lyric line
(text, translation, tokens, status and optional ASR span).  The legacy matcher
still exposes only validated spans for older callers; milliseconds remain
server-owned and are always derived from ASR words.
"""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

from lovktv.agents.ja_lyrics import (
    agent_api_key,
    agent_base_url,
    agent_model,
)
from lovktv.domain.alignment import (
    AgentAlignment,
    GeneratedLyrics,
    parse_alignment_payload,
    parse_generated_lyrics,
)
from lovktv.pipeline.lyrics import drop_credit_lines
from lovktv.pipeline.matching import _usable_asr_words

# v4 stores the complete status-bearing contract alongside legacy matches.
# Any old sparse cache is intentionally regenerated.
ALIGN_SCHEMA = "lovktv-align-v4"
GENERATE_SCHEMA = "lovktv-generated-lyrics-v1"
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)

SYSTEM = """Generate a complete karaoke lyric document from known lyrics and
the ASR transcript. Return JSON only in this shape:
{\"rows\":[{\"lyric\":1,\"status\":\"matched\",\"from\":3,\"to\":8}],\"groups\":[]}.

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
7. Do not silently skip any known lyric line. Every numbered lyric line must
   appear exactly once in `rows`. Use `matched` for a reliable ASR span,
   `uncertain` for a weak but real span, and `inferred` when ASR missed the
   words but repeated-chorus/context proves the line belongs there. Use
   `absent` only when the audio demonstrably omits the line. Inferred/absent
   rows have no ASR span and must include a concise `reason`. Never invent ASR
   indices and do not return rewritten lyric text. Every row must preserve the
   source `text`, provide a line-level `translation`, and split the line into
   ordered `tokens`; each token is one word/unit and has its own `translation`.
   Japanese tokens keep kanji readings and token-corresponding romaji. English
   embedded in another language is split as ordinary words; never put a whole
   sentence translation into the first token.
8. When several consecutive known lines form a verse/chorus block and the ASR
   contains only its beginning or ending, mark the unresolved middle lines in
   `missing` in their original order. The server will restore their timing
   from neighboring anchors; do not replace them with a different lyric line.
"""

GENERATE_SYSTEM = """You generate the complete karaoke lyric result from the
known lyric lines and a Whisper transcript. Return JSON only:
{"schema":"lovktv-generated-lyrics-v1","language":"en","rows":[
 {"lyric":1,"status":"matched","text":"from now on","translation":"从现在起",
  "from":1,"to":3,"tokens":[{"surface":"from","translation":"从"}]}
],"groups":[]}.

Rules:
1. Return exactly one row for every numbered lyric line, in lyric-number order.
`text` must be the exact source lyric line; never rewrite or omit it.
2. Use `matched` when the line is present in the transcript and provide the
1-based inclusive ASR word span. Use `uncertain` for a weak but real span,
`inferred` when context proves the line but ASR missed it, and `absent` only
when the recording demonstrably omits it. If a known lyric line falls between
two matched lines in the same section, treat an ASR gap as `inferred` and
return the complete known line and tokens; do not call it `absent` merely
because Whisper omitted its words. Inferred/absent rows must omit
`from`/`to` and include a concise `reason`.
3. `translation` is a faithful, clear Simplified Chinese translation of the
whole line. Keep the meaning, agency, negation, tense and emotional tone.
4. `tokens` cover the whole line in order. Each token has `surface` and a
short contextual Chinese `translation`; for English use exactly one token per
word (including words such as from, a, and). Do not put the whole-line
translation in one token. Japanese tokens may also include `reading`, `romaji`
and `pronunciation`.
5. ASR spans are references only; use the numbered transcript timestamps as the
timing source and never invent indices. Repeated lines must use their actual
occurrence. Do not return a matches-only object.
"""


def _source_hash(lines: list[str], words: list[dict[str, Any]], language: str) -> str:
    payload = json.dumps(
        {"schema": ALIGN_SCHEMA, "language": language, "lines": lines, "words": words},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        raise ValueError("对齐 agent 返回的不是 JSON 对象")
    return data


def _parse_alignment(raw: str, lyric_count: int | None = None, word_count: int | None = None) -> AgentAlignment:
    return parse_alignment_payload(_json_payload(raw), lyric_count=lyric_count, word_count=word_count)


def _parse(raw: str) -> list[dict[str, int]]:
    """Parse both protocol versions and expose legacy matched rows."""
    return _parse_legacy_rows(_json_payload(raw))


def _parse_legacy_rows(data: dict[str, Any]) -> list[dict[str, int]]:
    rows = data.get("matches")
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


def _request_content(messages: list[dict[str, str]]) -> str:
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
    return str(content)


def _complete(messages: list[dict[str, str]]) -> GeneratedLyrics | AgentAlignment | list[dict[str, int]]:
    """Call the configured model and parse either the v1 or legacy response.

    Returning the validated object here lets callers retain ``missing`` and
    ``inferred`` rows while the list branch keeps monkey-patched integrations
    and older tests/source-compatible adapters working.
    """
    payload = _json_payload(_request_content(messages))
    # New protocol is status-bearing.  Keep accepting the old matches-only
    # object so an older configured gateway does not disable alignment.
    if isinstance(payload.get("rows"), list):
        rows = payload.get("rows") or []
        if rows and any(isinstance(row, dict) and "text" in row for row in rows):
            # A partially generated document is not a valid legacy response;
            # reject it so the caller can fall back deterministically.
            return parse_generated_lyrics(payload)
        return parse_alignment_payload(payload)
    if "missing" in payload:
        return parse_alignment_payload(payload)
    return _parse_legacy_rows(payload)


def _build_messages(
    line_specs: list[str], words: list[dict[str, Any]], language: str,
    *, system: str = SYSTEM,
) -> list[dict[str, str]]:
    numbered_lines = "\n".join(f"{i}. {spec}" for i, spec in enumerate(line_specs, 1))
    numbered_words = "\n".join(
        f"{int(word.get('index') or i)}. [{word['start_ms']}-{word['end_ms']}] {word['text']}"
        for i, word in enumerate(words, 1)
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Language: {language}\nKnown lyric lines:\n{numbered_lines}\n\n"
                f"Whisper ASR words:\n{numbered_words}"
            ),
        },
    ]


def _build_generation_messages(
    line_specs: list[str], words: list[dict[str, Any]], language: str,
    *, line_numbers: list[int] | None = None, context: str = "",
) -> list[dict[str, str]]:
    ids = line_numbers or list(range(1, len(line_specs) + 1))
    numbered_lines = "\n".join(f"{i}. {spec}" for i, spec in zip(ids, line_specs))
    numbered_words = "\n".join(
        f"{int(word.get('index') or i)}. [{word['start_ms']}-{word['end_ms']}] {word['text']}"
        for i, word in enumerate(words, 1)
    )
    return [
        {"role": "system", "content": GENERATE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Language: {language}\nKnown lyric lines:\n{numbered_lines}\n\n"
                + (f"Neighboring lyric context (do not return these lines):\n{context}\n\n" if context else "")
                + f"Whisper ASR words:\n{numbered_words}"
            ),
        },
    ]


def _generation_line_specs(lines: list[dict[str, Any]]) -> tuple[list[int], list[str]]:
    numbers: list[int] = []
    specs: list[str] = []
    for number, item in enumerate(lines, 1):
        start = item.get("ms")
        end = item.get("end_ms")
        clock = (
            f"[{int(start)}-{int(end) if end is not None else '?'}] "
            if start is not None
            else "[no timestamp] "
        )
        numbers.append(number)
        specs.append(clock + str(item.get("text") or ""))
    return numbers, specs


def _generate_chunk(
    lines: list[dict[str, Any]],
    words: list[dict[str, Any]],
    language: str,
    *,
    global_numbers: list[int] | None = None,
    context: str = "",
    word_count: int | None = None,
    allowed_word_indices: set[int] | None = None,
) -> GeneratedLyrics:
    local_numbers, specs = _generation_line_specs(lines)
    ids = global_numbers or local_numbers
    payload = _json_payload(
        _request_content(
            _build_generation_messages(
                specs, words, language, line_numbers=ids, context=context
            )
        )
    )
    source_by_id = {
        number: str(item.get("text") or "")
        for number, item in zip(ids, lines)
    }
    for row in payload.get("rows") or []:
        if isinstance(row, dict):
            try:
                number = int(row.get("lyric"))
            except (TypeError, ValueError):
                continue
            if number in source_by_id:
                # Preserve authored source text exactly; tolerate harmless
                # punctuation/case edits while validating token coverage.
                row["text"] = source_by_id[number]
            if (
                allowed_word_indices is not None
                and isinstance(row.get("from"), int)
                and isinstance(row.get("to"), int)
                and not set(range(row["from"], row["to"] + 1)).issubset(allowed_word_indices)
            ):
                row.pop("from", None)
                row.pop("to", None)
                row["status"] = "inferred"
                row["reason"] = "ASR 片段超出本段时间窗口，保留歌词并交由时间轴推断"
    return parse_generated_lyrics(payload, expected_lyrics=set(ids), word_count=word_count or len(words))


def _recover_obvious_spans(
    generated: GeneratedLyrics,
    lines: list[dict[str, Any]],
    words: list[dict[str, Any]],
) -> GeneratedLyrics:
    """Recover exact ASR phrases a cautious model marked absent.

    This is deliberately conservative and only upgrades a row when a
    contiguous ASR window has a near-exact lexical match near that line's LRC
    clock. It prevents a model's uncertainty from turning clearly sung
    repeated hooks into silent omissions, while leaving genuinely missing
    lines as ``inferred``/``absent``.
    """
    by_id = {index: item for index, item in enumerate(lines, 1)}
    used = {
        index
        for row in generated.rows
        if row.from_ is not None and row.to is not None
        for index in range(row.from_, row.to + 1)
    }
    out: list[dict[str, Any]] = []
    for row in generated.rows:
        data = row.model_dump(mode="json", by_alias=True)
        if row.from_ is None or row.to is None:
            source = str(by_id.get(row.lyric, {}).get("text") or row.text)
            wanted = [part.casefold() for part in re.findall(r"[\w']+", source, re.UNICODE)]
            if wanted:
                clock = int(by_id.get(row.lyric, {}).get("ms") or 0)
                candidates: list[tuple[float, int, int]] = []
                for start in range(len(words)):
                    if abs(int(words[start].get("start_ms") or 0) - clock) > 15_000:
                        continue
                    for size in range(max(1, len(wanted) - 1), len(wanted) + 3):
                        end = start + size
                        if end > len(words):
                            continue
                        if any(index in used for index in range(start + 1, end + 1)):
                            continue
                        heard = [
                            part.casefold()
                            for word in words[start:end]
                            for part in re.findall(r"[\w']+", str(word.get("text") or ""), re.UNICODE)
                        ]
                        score = SequenceMatcher(None, wanted, heard).ratio()
                        if score >= 0.82:
                            candidates.append((score, start + 1, end))
                if candidates:
                    _score, from_, to = max(candidates, key=lambda item: (item[0], -abs(item[1] - 1)))
                    data.update(status="uncertain", **{"from": from_, "to": to})
                    data["reason"] = "ASR 与原歌词存在连续高置信词序，恢复为不确定匹配"
                    used.update(range(from_, to + 1))
        out.append(data)
    return parse_generated_lyrics(
        {"schema": GENERATE_SCHEMA, "language": generated.language, "rows": out, "groups": []},
        lyric_count=len(lines),
        word_count=len(words),
    )


def generate_lyrics_with_agent(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    *,
    cache_path: Path | None = None,
) -> GeneratedLyrics | None:
    """Ask the model to generate the complete, tokenized lyric document.

    This is intentionally separate from the legacy timeline adapter: callers
    can inspect and review the generation result before converting its timing
    anchors into ``lyrics.json``.  No model output is written directly to the
    persisted timeline.
    """
    if not agent_base_url() or not agent_api_key() or not asr_words:
        return None
    kept = [
        item
        for item in drop_credit_lines(lines, language)
        if str(item.get("text") or "").strip()
    ]
    words = [
        {
            "index": index,
            "text": str(item.get("text") or ""),
            "start_ms": int(item.get("start_ms") or 0),
            "end_ms": int(item.get("end_ms") or item.get("start_ms") or 0),
        }
        for index, item in enumerate(_usable_asr_words(asr_words), 1)
        if str(item.get("text") or "").strip()
    ][:800]
    if not kept or not words:
        return None
    _numbers, line_specs = _generation_line_specs(kept)
    digest = hashlib.sha256(
        json.dumps(
            {"schema": GENERATE_SCHEMA, "language": language, "lines": line_specs, "words": words},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("schema") == GENERATE_SCHEMA and cached.get("source_hash") == digest:
                parsed = parse_generated_lyrics(cached, lyric_count=len(kept), word_count=len(words))
                if any(parsed.rows[i - 1].text != str(kept[i - 1].get("text") or "") for i in range(1, len(kept) + 1)):
                    raise ValueError("generated lyric text does not match source lines")
                return parsed
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    generated: GeneratedLyrics | None = None
    # A whole-song response is preferred because it gives the model global
    # context for repeated choruses.  Long songs can exceed the gateway's
    # completion limit, so retry in bounded sections and merge only after the
    # same schema validator checks every section and every ASR span.
    if len(kept) <= 24:
        try:
            payload = _json_payload(
                _request_content(_build_generation_messages(line_specs, words, language))
            )
            source_by_id = {
                number: str(item.get("text") or "")
                for number, item in enumerate(kept, 1)
            }
            for row in payload.get("rows") or []:
                if isinstance(row, dict):
                    try:
                        number = int(row.get("lyric"))
                    except (TypeError, ValueError):
                        continue
                    if number in source_by_id:
                        row["text"] = source_by_id[number]
            generated = parse_generated_lyrics(
                payload, lyric_count=len(kept), word_count=len(words)
            )
        except Exception:
            generated = None
    if generated is None:
        chunk_size = 16
        chunk_rows = []
        occupied: set[int] = set()
        try:
            for offset in range(0, len(kept), chunk_size):
                chunk = kept[offset : offset + chunk_size]
                ids = list(range(offset + 1, offset + 1 + len(chunk)))
                before = str(kept[offset - 1].get("text") or "") if offset else ""
                after_index = offset + len(chunk)
                after = str(kept[after_index].get("text") or "") if after_index < len(kept) else ""
                context = "\n".join(
                    part for part in (
                        f"before: {before}" if before else "",
                        f"after: {after}" if after else "",
                    ) if part
                )
                chunk_start = int(chunk[0].get("ms") or 0)
                chunk_end = int(chunk[-1].get("end_ms") or chunk[-1].get("ms") or chunk_start)
                window_words = [
                    word for word in words
                    if int(word.get("end_ms") or 0) >= chunk_start - 12_000
                    and int(word.get("start_ms") or 0) <= chunk_end + 12_000
                ] or words
                part = _generate_chunk(
                    chunk,
                    window_words,
                    language,
                    global_numbers=ids,
                    context=context,
                    word_count=len(words),
                    allowed_word_indices={int(word.get("index") or 0) for word in window_words},
                )
                for row in part.rows:
                    row_data = row.model_dump(mode="json", by_alias=True)
                    if row.from_ is not None and row.to is not None:
                        span = set(range(row.from_, row.to + 1))
                        if occupied.intersection(span):
                            # Two independently generated sections may choose
                            # the same repeated chorus occurrence. Preserve the
                            # line and its translation, but remove the unsafe
                            # anchor so the deterministic LRC/ASR path places
                            # it instead of dropping the whole document.
                            row_data.pop("from", None)
                            row_data.pop("to", None)
                            row_data["status"] = "inferred"
                            row_data["reason"] = "分段生成的 ASR 片段与另一段重复，保留歌词并交由时间轴推断"
                        else:
                            occupied.update(span)
                    chunk_rows.append(row_data)
            generated = parse_generated_lyrics(
                {
                    "schema": GENERATE_SCHEMA,
                    "language": language,
                    "rows": chunk_rows,
                    "groups": [],
                },
                lyric_count=len(kept),
                word_count=len(words),
            )
        except Exception:
            return None
    if generated is None:
        return None
    try:
        generated = _recover_obvious_spans(generated, kept, words)
    except Exception:
        # Metadata is still useful when recovery cannot be applied; the
        # original, schema-validated rows remain the source of truth.
        pass
    if any(
        generated.rows[i - 1].text != str(kept[i - 1].get("text") or "")
        for i in range(1, len(kept) + 1)
    ):
        return None
    if cache_path:
        try:
            cache_path.write_text(
                json.dumps(
                    {
                        **generated.model_dump(mode="json", by_alias=True),
                        "schema": GENERATE_SCHEMA,
                        "source_hash": digest,
                        "model": agent_model(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
    return generated


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
        # The alignment entry point now asks for the complete generated
        # document.  The legacy matcher list is derived only after the
        # document passes the status/token schema validator.
        matches = _complete(
            _build_messages(line_specs, words, language, system=GENERATE_SYSTEM)
        )
        generated = matches if isinstance(matches, GeneratedLyrics) else None
        alignment = matches if isinstance(matches, AgentAlignment) else None
        if generated is not None:
            generated = parse_generated_lyrics(
                generated.model_dump(mode="json", by_alias=True),
                lyric_count=len(kept),
                word_count=len(words),
            )
            matches = generated.legacy_matches()
        elif alignment is not None:
            # Enforce complete source coverage at the Python boundary.  A
            # A valid-looking response that omitted a line must fail closed
            # instead of silently degrading into a sparse legacy list.
            alignment = parse_alignment_payload(
                alignment.model_dump(mode="json", by_alias=True),
                lyric_count=len(kept),
                word_count=len(words),
            )
            matches = alignment.legacy_matches()
        valid = _validate(matches, len(kept), len(words))
    except Exception:
        return []
    if cache_path:
        try:
            cache_path.write_text(
                json.dumps(
                    {
                        "schema": ALIGN_SCHEMA,
                        "source_hash": digest,
                        "matches": valid,
                        **(
                            {"generated": generated.model_dump(mode="json", by_alias=True)}
                            if generated is not None
                            else (
                                {"alignment": alignment.model_dump(mode="json", by_alias=True)}
                                if alignment is not None
                                else {}
                            )
                        ),
                    },
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
