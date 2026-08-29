"""Turn LRC lines into karaoke timeline: zh per character, ja singable kana, en per word."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from lovktv.pipeline.language import detect_language

_KATAKANA = re.compile(r"[\u30a0-\u30ff]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_KANJI = re.compile(r"[\u3400-\u9fff\uf900-\ufaff々]")
_HAN = re.compile(r"[\u4e00-\u9fff]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_KATA_MARK = set("ー・ヽヾ")
_LATIN_CHUNK = re.compile(r"[A-Za-z0-9']+(?:[!?.,…]+)?")
_JA_CHUNK = re.compile(r"[A-Za-z0-9']+(?:[!?.,…]+)?|[^\sA-Za-z0-9']+")
_META_LINE = re.compile(r"^\[(ti|ar|al|by|offset):", re.I)
_converter = None


_ZH_GLOSS = re.compile(
    r"[这那吗吧呢们您说还让给从个为应后发对没会现过气头里东车门长关问听觉爱时什么只的了着总够就当做些积攒验]"
)


def looks_like_zh_translation(text: str) -> bool:
    """NetEase ja/en LRC often inserts a Simplified-Chinese gloss after each sung line."""
    body = unicodedata.normalize("NFKC", text or "")
    if _KANA.search(body) or _LATIN_LETTER.search(body):
        return False
    if len(_HAN.findall(body)) < 2:
        return False
    return bool(_ZH_GLOSS.search(body))


def drop_translation_lines(lines: list[dict[str, Any]], language: str | None) -> list[dict[str, Any]]:
    if language not in {"ja", "en"}:
        return lines
    return [item for item in lines if not looks_like_zh_translation(str(item.get("text") or ""))]


def drop_leading_title_echo(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Skip a 0:00 title line that is repeated when the vocal actually starts."""
    if len(lines) < 2:
        return lines
    first, second = lines[0], lines[1]
    if first.get("ms") is None or int(first["ms"]) >= 1000:
        return lines
    if str(first.get("text") or "").strip() != str(second.get("text") or "").strip():
        return lines
    return list(lines[1:])


_CREDIT_LINE = re.compile(
    r"(収録\s*[:：]|発売日\s*[:：]|^\s*「[^」]{1,48}」\s*(OP|ED)?\s*$)",
)
# NetEase ja LRC often ships Simplified Chinese lookalikes of Japanese kanji.
_CN_TO_JP = str.maketrans(
    {
        "时": "時",
        "间": "間",
        "谁": "誰",
        "试": "試",
        "梦": "夢",
        "伤": "傷",
        "计": "計",
        "绝": "絶",
        "强": "強",
        "经": "経",
        "历": "歴",
        "发": "発",
        "对": "対",
        "门": "門",
        "长": "長",
        "关": "関",
        "问": "問",
        "听": "聴",
        "觉": "覚",
        "爱": "愛",
        "应": "応",
        "后": "後",
        "东": "東",
        "车": "車",
        "图": "図",
        "语": "語",
        "说": "説",
        "处": "処",
        "单": "単",
        "传": "伝",
        "转": "転",
        "轻": "軽",
        "边": "辺",
        "达": "達",
        "过": "過",
        "为": "為",
        "从": "従",
        "个": "個",
        "开": "開",
        "实": "実",
        "现": "現",
        "气": "気",
        "飞": "飛",
        "风": "風",
        "读": "読",
        "无": "無",
        "两": "両",
        "并": "並",
        "种": "種",
        "终": "終",
        "纪": "紀",
        "续": "続",
        "乐": "楽",
        "欢": "歓",
        "卖": "売",
        "买": "買",
        "电": "電",
        "脑": "脳",
        "残": "残",
    }
)


def fold_ja_netease_kanji(text: str) -> str:
    """Turn NetEase Simplified lookalikes into Japanese kanji so ASR/furigana can match."""
    return unicodedata.normalize("NFKC", text or "").translate(_CN_TO_JP)


def is_credit_lyric(text: str) -> bool:
    body = unicodedata.normalize("NFKC", text or "").strip()
    if not body:
        return True
    if _CREDIT_LINE.search(body):
        return True
    if body.startswith("収録") or body.startswith("発売"):
        return True
    return False


def drop_credit_lines(lines: list[dict[str, Any]], language: str | None = None) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in lines:
        text = str(item.get("text") or "")
        if language == "ja":
            text = fold_ja_netease_kanji(text)
        if is_credit_lyric(text):
            continue
        row = dict(item)
        row["text"] = text
        cleaned.append(row)
    return cleaned


def prepare_lyric_lines(lines: list[dict[str, Any]], language: str | None) -> list[dict[str, Any]]:
    return drop_credit_lines(drop_leading_title_echo(drop_translation_lines(lines, language)), language)


def _kakasi():
    global _converter
    if _converter is None:
        from pykakasi import kakasi

        _converter = kakasi()
    return _converter


def _ja_units(text: str) -> list[dict[str, str]]:
    source = unicodedata.normalize("NFKC", text)
    try:
        return [dict(part) for part in _kakasi().convert(source)]
    except Exception:
        return [{"orig": char, "hira": char, "hepburn": ""} for char in source if not char.isspace()]


def _is_katakana(text: str) -> bool:
    body = [char for char in text if not char.isspace()]
    return bool(body) and all(_KATAKANA.match(char) or char in _KATA_MARK for char in body)


def _ja_native_specs(text: str) -> list[tuple[str, str]]:
    specs: list[tuple[str, str]] = []
    for unit in _ja_units(text):
        orig = str(unit.get("orig") or "")
        hira = str(unit.get("hira") or orig)
        if not orig.strip():
            continue
        if _LATIN_CHUNK.fullmatch(orig.strip()):
            specs.append((orig.strip(), ""))
            continue
        if _is_katakana(orig):
            specs.append((orig, ""))
            continue
        if _KANJI.search(orig):
            surface = "".join(char for char in orig if not char.isspace())
            reading = "".join(char for char in hira if not char.isspace())
            if surface:
                specs.append((surface, "" if reading == surface else reading))
            continue
        for char in orig:
            if not char.isspace():
                specs.append((char, ""))
    return specs


def ja_token_specs(text: str) -> list[tuple[str, str]]:
    """Offline fallback: display kanji, hiragana reading above. Katakana unlabeled.

    Latin words in a Japanese line stay whole. Loanword English labels and
    contextual readings come from the ja-lyrics agent.
    """
    specs: list[tuple[str, str]] = []
    source = unicodedata.normalize("NFKC", text)
    for chunk in _JA_CHUNK.finditer(source):
        piece = chunk.group(0)
        if _LATIN_CHUNK.fullmatch(piece):
            specs.append((piece, ""))
            continue
        specs.extend(_ja_native_specs(piece))
    return specs


def _latin_words(text: str) -> list[str]:
    return [part for part in re.findall(r"[A-Za-z0-9']+|[^\sA-Za-z0-9']+", text) if part.strip()]


def tokenize(text: str, language: str) -> list[str]:
    if language == "ja":
        return [piece for piece, _label in ja_token_specs(text)]
    if language == "en" or (_LATIN_LETTER.search(text) and not _HAN.search(text) and not _KANA.search(text)):
        return _latin_words(text)
    return [char for char in text if not char.isspace()]


def reading_for(token: str, language: str) -> str:
    if language != "ja":
        return ""
    specs = ja_token_specs(token)
    if len(specs) == 1:
        return specs[0][1]
    return "".join(label for _piece, label in specs if label)


def parse_plain_lines(raw: str) -> list[dict[str, Any]]:
    """Untimed lyric lines. LRC meta / empty rows are skipped."""
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text or _META_LINE.match(text) or text.startswith("["):
            continue
        out.append({"ms": None, "text": text})
    return out


def build_cue(
    text: str,
    start_ms: int,
    end_ms: int,
    language: str,
    token_spans: list[tuple[int, int]] | None = None,
) -> dict[str, Any] | None:
    if language == "ja":
        specs = ja_token_specs(text)
        tokens = [piece for piece, _label in specs]
        labels = [label for _piece, label in specs]
    else:
        tokens = tokenize(text, language)
        labels = [reading_for(token, language) for token in tokens]
    if not tokens:
        return None
    end_ms = max(start_ms + 200, end_ms)
    if not token_spans or len(token_spans) != len(tokens):
        span = max(end_ms - start_ms, 200)
        unit = span / len(tokens)
        token_spans = []
        cursor = start_ms
        for index, _token in enumerate(tokens):
            token_end = end_ms if index == len(tokens) - 1 else int(cursor + unit)
            token_spans.append((int(cursor), token_end))
            cursor = token_end
    token_rows = []
    for token, label, (token_start, token_end) in zip(tokens, labels, token_spans):
        token_rows.append(
            {
                "text": token,
                "start_ms": int(token_start),
                "end_ms": int(max(token_start + 40, token_end)),
                "reading": label,
            }
        )
    token_rows[-1]["end_ms"] = end_ms
    return {
        "text": text,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "tokens": token_rows,
    }


def timeline_from_lrc(
    lines: list[dict[str, Any]],
    language: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    joined = "".join(item.get("text") or "" for item in lines)
    lang = detect_language(joined, language)
    cues: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        start_ms = int(line["ms"])
        if line.get("end_ms") is not None:
            end_ms = max(start_ms + 200, int(line["end_ms"]))
        elif index + 1 < len(lines):
            end_ms = max(start_ms + 200, int(lines[index + 1]["ms"]))
        elif duration_ms:
            end_ms = max(start_ms + 200, duration_ms)
        else:
            end_ms = start_ms + 4000
        cue = build_cue(str(line.get("text") or ""), start_ms, end_ms, lang)
        if cue:
            cues.append(cue)
    return {"language": lang, "alignment": "lrc-interp", "alignment_source": "", "cues": cues}


def _shift_one(cue: dict[str, Any], delta_ms: int) -> None:
    cue["start_ms"] = int(cue.get("start_ms") or 0) + delta_ms
    cue["end_ms"] = int(cue.get("end_ms") or 0) + delta_ms
    for token in cue.get("tokens") or []:
        token["start_ms"] = int(token.get("start_ms") or 0) + delta_ms
        token["end_ms"] = int(token.get("end_ms") or 0) + delta_ms


def _fit_tokens(cue: dict[str, Any], start_ms: int, end_ms: int) -> None:
    tokens = list(cue.get("tokens") or [])
    if not tokens:
        return
    span = max(end_ms - start_ms, 200)
    old_start = int(tokens[0].get("start_ms") or start_ms)
    old_end = int(tokens[-1].get("end_ms") or end_ms)
    old_span = max(old_end - old_start, 1)
    for token in tokens:
        rel_s = (int(token.get("start_ms") or old_start) - old_start) / old_span
        rel_e = (int(token.get("end_ms") or old_end) - old_start) / old_span
        token["start_ms"] = start_ms + int(span * rel_s)
        token["end_ms"] = max(token["start_ms"] + 40, start_ms + int(span * rel_e))
    tokens[0]["start_ms"] = start_ms
    tokens[-1]["end_ms"] = end_ms


def repair_cue_order(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, cue in enumerate(cues):
        prev_end = int(cues[index - 1]["end_ms"]) if index else 0
        nxt = int(cues[index + 1]["start_ms"]) if index + 1 < len(cues) else None
        start_ms = max(0, prev_end, int(cue.get("start_ms") or 0))
        end_ms = max(start_ms + 200, int(cue.get("end_ms") or 0))
        if nxt is not None and end_ms > nxt:
            end_ms = nxt
            if end_ms < start_ms + 200:
                start_ms = max(prev_end, nxt - 200)
                end_ms = nxt
        _fit_tokens(cue, start_ms, end_ms)
        cue["start_ms"] = start_ms
        cue["end_ms"] = end_ms
    return cues


def shift_cues(
    cues: list[dict[str, Any]],
    index: int,
    delta_ms: int,
    rest: bool = False,
) -> list[dict[str, Any]]:
    """Move one line, or this line and every line after it."""
    if not cues or index < 0 or index >= len(cues):
        raise ValueError("没有这句歌词")
    out = []
    for cue in cues:
        row = dict(cue)
        row["tokens"] = [dict(token) for token in (cue.get("tokens") or [])]
        out.append(row)
    last = len(out) if rest else index + 1
    for pos in range(index, last):
        _shift_one(out[pos], int(delta_ms))
    return repair_cue_order(out)


def write_manual_lrc(out_dir: Path, cues: list[dict[str, Any]]) -> None:
    """Lock line starts so auto-realign cannot overwrite editor timing."""
    lines = []
    for cue in cues:
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{_lrc_time(int(cue['start_ms']))}]{text}")
    if not lines:
        return
    (out_dir / "lyrics.manual.lrc").write_text("\n".join(lines) + "\n", encoding="utf-8")


def rebuild_manual_timeline(
    rows: list[dict[str, Any]],
    existing: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    """Build a locked timeline: each line holds until the next line starts."""
    old = list((existing or {}).get("cues") or [])
    used: set[int] = set()
    cues: list[dict[str, Any]] = []
    language = str((existing or {}).get("language") or detect_language(
        "".join(str(row.get("text") or "") for row in rows)
    ))
    for index, row in enumerate(rows):
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        start_ms = int(row["ms"] if row.get("ms") is not None else row.get("start_ms") or 0)
        if index + 1 < len(rows):
            nxt = rows[index + 1]
            end_ms = int(nxt["ms"] if nxt.get("ms") is not None else nxt.get("start_ms") or start_ms + 4000)
        elif duration_ms:
            end_ms = max(start_ms + 1200, min(int(duration_ms), start_ms + 8000))
        else:
            end_ms = start_ms + 4000
        end_ms = max(start_ms + 400, end_ms)
        matched = None
        for cue_i, cue in enumerate(old):
            if cue_i in used:
                continue
            if str(cue.get("text") or "").strip() == text:
                matched = {
                    "text": text,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "tokens": [dict(token) for token in (cue.get("tokens") or [])],
                }
                used.add(cue_i)
                break
        if matched and matched["tokens"]:
            _fit_tokens(matched, start_ms, end_ms)
            cues.append(matched)
        else:
            cue = build_cue(text, start_ms, end_ms, language)
            if cue:
                cues.append(cue)
    return validate_timeline(
        {
            "language": language,
            "alignment": "manual",
            "cues": cues,
        }
    )


def validate_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("cues")
    if not isinstance(raw, list) or not raw:
        raise ValueError("没有歌词")
    cues: list[dict[str, Any]] = []
    for item in raw:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start_ms = int(item.get("start_ms") or 0)
        end_ms = max(start_ms + 200, int(item.get("end_ms") or 0))
        tokens = []
        for token in item.get("tokens") or []:
            tok_text = str(token.get("text") or "")
            if not tok_text:
                continue
            tokens.append(
                {
                    "text": tok_text,
                    "start_ms": int(token.get("start_ms") or start_ms),
                    "end_ms": int(token.get("end_ms") or end_ms),
                    "reading": str(token.get("reading") or ""),
                }
            )
        cues.append(
            {
                "text": text,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "tokens": tokens,
            }
        )
    if not cues:
        raise ValueError("没有歌词")
    repair_cue_order(cues)
    return {
        "language": str(payload.get("language") or "zh"),
        "alignment": str(payload.get("alignment") or "manual"),
        "alignment_source": "manual",
        "cues": cues,
    }


def write_subtitles(timeline: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lyrics.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    elrc_lines = []
    ass_events = []
    for cue in timeline["cues"]:
        start = _ass_time(cue["start_ms"])
        end = _ass_time(cue["end_ms"])
        k_parts = []
        word_bits = []
        for token in cue["tokens"]:
            cs = max(1, int(round((token["end_ms"] - token["start_ms"]) / 10)))
            k_parts.append(rf"{{\k{cs}}}{token['text']}")
            word_bits.append(f"<{token['start_ms']}> {token['text']}")
        elrc_lines.append(f"[{_lrc_time(cue['start_ms'])}]{''.join(word_bits)}")
        ass_events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{''.join(k_parts)}")
    (out_dir / "lyrics.elrc").write_text("\n".join(elrc_lines) + "\n", encoding="utf-8")
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Noto Sans CJK SC,64,&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,"
        "0,0,0,0,100,100,0,0,1,3,0,2,40,40,80,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    (out_dir / "lyrics.ass").write_text(header + "\n".join(ass_events) + "\n", encoding="utf-8")


def _lrc_time(ms: int) -> str:
    minutes, rem = divmod(ms, 60000)
    seconds, milli = divmod(rem, 1000)
    return f"{minutes:02d}:{seconds:02d}.{milli:03d}"


def _ass_time(ms: int) -> str:
    hours, rem = divmod(ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, milli = divmod(rem, 1000)
    cs = milli // 10
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"
