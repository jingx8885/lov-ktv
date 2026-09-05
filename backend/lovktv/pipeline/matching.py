"""Lyric/ASR normalization and token matching helpers."""

from __future__ import annotations

import re
from statistics import median
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from lovktv.pipeline.constants import *
from lovktv.pipeline.lyrics import fold_ja_netease_kanji

_WORD = re.compile(r"[A-Za-z0-9']+")
_JA_LEAD_FILLER = re.compile(r"^[あぁアァー]+")


def _norm_word(text: str) -> str:
    return "".join(_WORD.findall((text or "").lower()))


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > 1:
        return 2
    prev = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        cur = [i]
        for j, b in enumerate(right, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a != b)))
        prev = cur
    return prev[-1]


def _en_word_eq(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) >= 5 and _edit_distance(left, right) <= 1:
        return True
    if min(len(left), len(right)) >= 4:
        longer, shorter = (left, right) if len(left) >= len(right) else (right, left)
        extra = longer[len(shorter) :]
        if longer.startswith(shorter) and extra in {"d", "ed", "ing", "s"}:
            return True
    return False


def _asr_window(
    asr_words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    return [
        word
        for word in asr_words
        if int(word.get("end_ms") or 0) > start_ms - 120
        and int(word.get("start_ms") or 0) < end_ms + 120
    ]


def _finish_token_hits(
    hits: list[tuple[int, int] | None],
    start_ms: int,
    end_ms: int,
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for index, hit in enumerate(hits):
        if hit:
            spans.append(hit)
            continue
        prev_end = spans[-1][1] if spans else start_ms
        nxt = end_ms
        for later in hits[index + 1 :]:
            if later:
                nxt = later[0]
                break
        right = max(prev_end + 40, min(nxt, prev_end + max(40, (nxt - prev_end) // 2)))
        spans.append((prev_end, right))
    cursor = start_ms
    fixed: list[tuple[int, int]] = []
    for index, (left, right) in enumerate(spans):
        left = max(cursor, left)
        right = max(left + 40, right)
        if index == len(spans) - 1:
            right = end_ms
        fixed.append((left, min(end_ms, right)))
        cursor = fixed[-1][1]
    fixed[0] = (start_ms, fixed[0][1])
    fixed[-1] = (fixed[-1][0], end_ms)
    return fixed


def _en_asr_token_spans(
    pieces: list[str],
    start_ms: int,
    end_ms: int,
    asr_words: list[dict[str, Any]],
) -> list[tuple[int, int]] | None:
    window = [
        word
        for word in _asr_window(asr_words, start_ms, end_ms)
        if _norm_word(str(word.get("text") or ""))
    ]
    if not window:
        return None
    # Punctuation is kept as a visual token, but it is not an ASR word.  Do
    # not let commas/quotes lower the lexical match ratio or make a good line
    # fall back to an untimed even split.
    lexical = [piece for piece in pieces if _norm_word(piece)]
    if not lexical:
        return None
    used = 0
    hits: list[tuple[int, int] | None] = []
    matched = 0
    for piece in pieces:
        key = _norm_word(piece)
        found = None
        limit = min(len(window), used + 4)
        for index in range(used, limit):
            if _en_word_eq(key, _norm_word(str(window[index].get("text") or ""))):
                found = index
                break
        if found is None:
            hits.append(None)
            continue
        used = found + 1
        matched += 1
        left = max(start_ms, int(window[found]["start_ms"]))
        right = min(end_ms, max(left + 40, int(window[found]["end_ms"])))
        hits.append((left, right))
    if matched < max(1, int(len(lexical) * 0.55)):
        return None
    return _finish_token_hits(hits, start_ms, end_ms)


def _cjk_asr_token_spans(
    pieces: list[str],
    start_ms: int,
    end_ms: int,
    asr_words: list[dict[str, Any]],
) -> list[tuple[int, int]] | None:
    chars: list[tuple[str, int, int]] = []
    for word in _asr_window(asr_words, start_ms, end_ms):
        text = "".join(ch for ch in str(word.get("text") or "") if not ch.isspace())
        if not text:
            continue
        left = int(word.get("start_ms") or 0)
        right = max(left + 40, int(word.get("end_ms") or left))
        unit = (right - left) / len(text)
        for index, char in enumerate(text):
            chars.append(
                (char, int(left + index * unit), int(left + (index + 1) * unit))
            )
    if not chars:
        return None
    used = 0
    hits: list[tuple[int, int] | None] = []
    matched_chars = 0
    total_chars = 0
    for piece in pieces:
        key = "".join(ch for ch in piece if not ch.isspace())
        total_chars += len(key)
        if not key:
            hits.append(None)
            continue
        hay = "".join(char for char, _left, _right in chars[used:])
        idx = hay.find(key)
        if idx < 0 or idx > 2:
            hits.append(None)
            continue
        found = used + idx
        used = found + len(key)
        matched_chars += len(key)
        left = max(start_ms, chars[found][1])
        right = min(end_ms, max(left + 40, chars[used - 1][2]))
        hits.append((left, right))
    if matched_chars < max(2, int(total_chars * 0.55)):
        return None
    return _finish_token_hits(hits, start_ms, end_ms)


def asr_token_spans(
    pieces: list[str],
    start_ms: int,
    end_ms: int,
    asr_words: list[dict[str, Any]],
    language: str,
) -> list[tuple[int, int]] | None:
    """Stick lyric tokens to ASR words inside the line. None = use energy split."""
    if not pieces or not asr_words:
        return None
    if language == "en":
        return _en_asr_token_spans(pieces, start_ms, end_ms, asr_words)
    if language in {"ja", "zh", "yue"}:
        return _cjk_asr_token_spans(pieces, start_ms, end_ms, asr_words)
    return None


def normalize_lyric(text: str, language: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    if language == "en":
        return " ".join(_WORD.findall(folded.lower()))
    if language == "ja":
        folded = fold_ja_netease_kanji(folded)
    compact = "".join(
        char
        for char in folded
        if not char.isspace() and char not in ".,!?;:·・。、\"'()[]"
    )
    if language == "ja":
        stripped = _JA_LEAD_FILLER.sub("", compact)
        if stripped:
            compact = stripped
    return compact


def vocal_phrases(
    regions: list[tuple[int, int]],
    merge_gap_ms: int = 480,
    min_ms: int = 500,
) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start_ms, end_ms in regions:
        if merged and start_ms - merged[-1][1] <= merge_gap_ms:
            merged[-1] = (merged[-1][0], end_ms)
        else:
            merged.append((start_ms, end_ms))
    return [item for item in merged if item[1] - item[0] >= min_ms]


def estimate_lrc_offset(
    lines: list[dict[str, Any]], phrases: list[tuple[int, int]]
) -> int:
    """Estimate a robust global LRC shift from the first few vocal onsets."""
    timed = [item for item in lines if item.get("ms") is not None]
    if not timed or not phrases:
        return 0
    first_expected = int(timed[0]["ms"])
    first_onset = min(phrases, key=lambda phrase: abs(phrase[0] - first_expected))[0]
    first_raw = first_onset - first_expected
    samples = [first_raw]
    for item in timed[1:5]:
        expected = int(item["ms"])
        target = expected + first_raw
        onset = min(phrases, key=lambda phrase: abs(phrase[0] - target))[0]
        samples.append(onset - expected)
    raw = first_raw if len(samples) <= 2 else int(median(samples))
    if abs(raw) < 1500:
        return 0
    agreeing = sum(abs(sample - raw) <= 700 for sample in samples)
    if len(samples) > 2 and agreeing < max(2, (len(samples) + 1) // 2):
        return 0
    return max(-2000, min(20000, raw))


def line_match_score(known: str, heard: str, language: str) -> float:
    """Order-aware score so a short chorus does not swallow a longer verse."""
    left = normalize_lyric(known, language)
    right = normalize_lyric(heard, language)
    if not left or not right:
        return 0.0
    if language == "en":
        kw = left.split()
        hw = right.split()
        used = [False] * len(hw)
        hit = 0
        for word in kw:
            for index, other in enumerate(hw):
                if not used[index] and _en_word_eq(word, other):
                    used[index] = True
                    hit += 1
                    break
        union = len(kw) + len(hw) - hit
        jacc = hit / union if union else 0.0
        prefix = 0
        for a, b in zip(kw, hw):
            if not _en_word_eq(a, b):
                break
            prefix += 1
        mapped = []
        claimed = [False] * len(kw)
        for word in hw:
            mapped.append(word)
            for index, known_word in enumerate(kw):
                if not claimed[index] and _en_word_eq(known_word, word):
                    claimed[index] = True
                    mapped[-1] = known_word
                    break
        seq = SequenceMatcher(None, kw, mapped).ratio()
        score = max(jacc, seq)
        if prefix >= 4 and prefix * 3 >= len(kw) * 2 and len(hw) <= len(kw) + 1:
            return max(score, 0.82)
        return score
    ratio = SequenceMatcher(None, left, right).ratio()
    length = min(len(left), len(right)) / max(len(left), len(right))
    return ratio * (0.65 + 0.35 * length)


def _join_asr(texts: list[str], language: str) -> str:
    return " ".join(texts) if language == "en" else "".join(texts)


def accept_score(language: str) -> float:
    return EN_ACCEPT if language == "en" else JA_ACCEPT


def _usable_asr_words(asr_words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop collapsed Whisper tags so they cannot open a line window."""
    usable: list[dict[str, Any]] = []
    for word in asr_words:
        start = int(word.get("start_ms") or 0)
        end = int(word.get("end_ms") or 0)
        if end - start < 40:
            continue
        usable.append(word)
    return usable


def _best_asr_window(
    known: str,
    asr_words: list[dict[str, Any]],
    texts: list[str],
    language: str,
    cursor: int,
    earliest: int | None,
    latest: int | None,
    min_score: float,
) -> tuple[float, int, int] | None:
    n = len(asr_words)
    if cursor >= n:
        return None
    known_n = len(known.split()) if language == "en" else max(1, len(known))
    max_width = max(3, min(36, known_n + 8))
    time_limit = (
        latest if latest is not None else int(asr_words[cursor]["start_ms"]) + 30000
    )
    best: tuple[float, int, int] | None = None
    for start in range(cursor, n):
        start_ms = int(asr_words[start]["start_ms"])
        if earliest is not None and start_ms < earliest:
            continue
        if start_ms > time_limit:
            break
        local: tuple[float, int, int] | None = None
        for width in range(1, max_width + 1):
            end = start + width
            if end > n:
                break
            window_ms = int(asr_words[end - 1]["end_ms"]) - start_ms
            if window_ms > MAX_LINE_MS + 2500:
                break
            heard = _join_asr(texts[start:end], language)
            score = line_match_score(known, heard, language)
            width_err = abs(width - known_n)
            if local is None or score > local[0] + 1e-9:
                local = (score, start, end)
            elif abs(score - local[0]) <= 1e-9:
                prev_err = abs((local[2] - local[1]) - known_n)
                if width_err < prev_err or (width_err == prev_err and end > local[2]):
                    local = (score, start, end)
        if local is None:
            continue
        if local[0] >= min_score:
            return local
        if best is None or local[0] > best[0] + 0.01:
            best = local
    if best and best[0] >= min_score:
        return best
    return None


def estimate_asr_offset(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
) -> int:
    """Shift from the first sung line only. Later lines must not walk the clock."""
    asr_words = _usable_asr_words(asr_words)
    if not asr_words:
        return 0
    texts = [str(item.get("text") or "") for item in asr_words]
    accept = accept_score(language)
    first = None
    for line in lines:
        if line.get("ms") is None or int(line["ms"]) < 1000:
            continue
        if normalize_lyric(str(line.get("text") or ""), language):
            first = line
            break
    if first is None:
        return 0
    expected = int(first["ms"])
    known = normalize_lyric(str(first.get("text") or ""), language)
    tight = _best_asr_window(
        known,
        asr_words,
        texts,
        language,
        0,
        expected - 2000,
        expected + ASR_WINDOW_AFTER,
        accept,
    )
    if tight:
        return int(asr_words[tight[1]]["start_ms"]) - expected
    wide = _best_asr_window(
        known,
        asr_words,
        texts,
        language,
        0,
        expected - 2000,
        expected + ASR_OFFSET_WIDE_AFTER,
        accept,
    )
    if not wide:
        return 0
    return max(-2000, min(20000, int(asr_words[wide[1]]["start_ms"]) - expected))


def match_score(known: str, heard: str, language: str) -> float:
    """Similarity for optional ASR anchoring. English is word-level and stricter."""
    if language == "en":
        left = set(part.lower() for part in _WORD.findall(known))
        right = set(part.lower() for part in _WORD.findall(heard))
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)
    left = [char for char in known if not char.isspace()]
    right = [char for char in heard if not char.isspace()]
    if not left or not right:
        return 0.0
    return len(set(left) & set(right)) / max(len(set(left) | set(right)), 1)


def match_threshold(language: str) -> float:
    return EN_MATCH_THRESHOLD if language == "en" else CJK_MATCH_THRESHOLD


def best_asr_span(
    line: str,
    asr_words: list[dict[str, Any]],
    language: str,
) -> tuple[int, int] | None:
    """Anchor a known line to ASR words. English must not use the CJK threshold."""
    if not asr_words:
        return None
    texts = [str(item.get("text") or "") for item in asr_words]
    best: tuple[float, int, int] | None = None
    for start in range(len(asr_words)):
        for end in range(start + 1, min(len(asr_words), start + 12) + 1):
            heard = (
                " ".join(texts[start:end])
                if language == "en"
                else "".join(texts[start:end])
            )
            score = match_score(line, heard, language)
            if best is None or score > best[0]:
                best = (score, start, end)
    if best is None or best[0] < match_threshold(language):
        return None
    _, start, end = best
    return int(asr_words[start]["start_ms"]), int(asr_words[end - 1]["end_ms"])
