"""Force-align known lyrics onto vocal energy / onsets.

LRC line times are a prior. Voice energy snaps line starts and
distributes zh/ja characters or English words inside each line.
Plain (untimed) lyrics are parked onto vocal-activity regions.
"""

from __future__ import annotations

import array
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
import wave
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from lovktv.pipeline.language import detect_language
from lovktv.pipeline.lyrics import (
    build_cue,
    drop_credit_lines,
    fold_ja_netease_kanji,
    prepare_lyric_lines,
    timeline_from_lrc,
    tokenize,
)

HOP_MS = 20
MAX_LINE_MS = 7000
HOLD_GAP_MS = 3000
MIN_LINE_MS = 500
ASR_WINDOW_BEFORE = 4000
ASR_WINDOW_AFTER = 4500
ASR_OFFSET_WIDE_AFTER = 20000
ASR_RESCUE_AFTER = 12000
LATE_ASR_SLACK_MS = 1800
EARLY_ASR_SLACK_MS = 800
CJK_MATCH_THRESHOLD = 0.28
EN_MATCH_THRESHOLD = 0.55
JA_ACCEPT = 0.62
EN_ACCEPT = 0.72
_WORD = re.compile(r"[A-Za-z0-9']+")
_JA_LEAD_FILLER = re.compile(r"^[あぁアァー]+")


def probe_duration_ms(path: Path) -> int:
    if not path.exists() or not shutil.which("ffprobe"):
        return 0
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        return max(0, int(float((result.stdout or "").strip()) * 1000))
    except ValueError:
        return 0


def extract_envelope(audio_path: Path, hop_ms: int = HOP_MS) -> tuple[list[float], int]:
    """Mono 16 kHz RMS envelope. Empty if ffmpeg/audio is missing."""
    if not audio_path.exists() or not shutil.which("ffmpeg"):
        return [], hop_ms
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "voice.wav"
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(audio_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(wav_path),
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 or not wav_path.exists():
            return [], hop_ms
        with wave.open(str(wav_path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            rate = handle.getframerate()
    hop = max(1, int(rate * hop_ms / 1000))
    samples = array.array("h")
    samples.frombytes(frames[: len(frames) - (len(frames) % 2)])
    envelope: list[float] = []
    for offset in range(0, len(samples), hop):
        chunk = samples[offset : offset + hop]
        if not chunk:
            break
        envelope.append(math.sqrt(sum(sample * sample for sample in chunk) / len(chunk)))
    return envelope, hop_ms


def vocal_regions(
    envelope: list[float],
    hop_ms: int = HOP_MS,
    min_ms: int = 80,
    merge_gap_ms: int = 200,
) -> list[tuple[int, int]]:
    if not envelope:
        return []
    ranked = sorted(envelope)
    median = ranked[len(ranked) // 2]
    p40 = ranked[int(len(ranked) * 0.40)]
    high = max(p40 * 1.5, median * 0.85, 40.0)
    low = max(high * 0.45, 20.0)
    active = False
    start = 0
    raw: list[tuple[int, int]] = []
    for index, value in enumerate(envelope):
        if not active and value >= high:
            active = True
            start = index * hop_ms
        elif active and value < low:
            raw.append((start, index * hop_ms))
            active = False
    if active:
        raw.append((start, len(envelope) * hop_ms))

    merged: list[tuple[int, int]] = []
    for start_ms, end_ms in raw:
        if end_ms - start_ms < min_ms:
            continue
        if merged and start_ms - merged[-1][1] <= merge_gap_ms:
            merged[-1] = (merged[-1][0], end_ms)
        else:
            merged.append((start_ms, end_ms))
    return merged


def snap_to_onset(
    target_ms: int,
    regions: list[tuple[int, int]],
    search_before: int = 1500,
    search_after: int = 800,
) -> int:
    window = (target_ms - search_before, target_ms + search_after)
    best = None
    best_delta = 10**9
    for start_ms, end_ms in regions:
        if end_ms < window[0] or start_ms > window[1]:
            continue
        onset = start_ms if window[0] <= start_ms <= window[1] else target_ms
        if start_ms <= target_ms <= end_ms:
            return start_ms if target_ms - start_ms < 400 else target_ms
        delta = abs(onset - target_ms)
        if delta < best_delta:
            best = start_ms
            best_delta = delta
    return best if best is not None else target_ms


def energy_token_spans(
    start_ms: int,
    end_ms: int,
    count: int,
    envelope: list[float],
    hop_ms: int = HOP_MS,
) -> list[tuple[int, int]]:
    """Slice [start, end) by cumulative energy. Falls back to even split."""
    if count <= 0:
        return []
    span = max(end_ms - start_ms, 200)
    even = []
    cursor = start_ms
    unit = span / count
    for index in range(count):
        token_end = end_ms if index == count - 1 else int(cursor + unit)
        even.append((int(cursor), token_end))
        cursor = token_end
    if not envelope:
        return even

    start_i = max(0, start_ms // hop_ms)
    end_i = min(len(envelope), max(start_i + 1, end_ms // hop_ms))
    window = envelope[start_i:end_i]
    total = sum(window)
    if total < 1e-6:
        return even

    cuts = [start_ms]
    acc = 0.0
    next_mark = 1
    for offset, value in enumerate(window):
        acc += value
        while next_mark < count and acc >= (next_mark / count) * total:
            cuts.append(start_ms + offset * hop_ms)
            next_mark += 1
    cuts.append(end_ms)
    while len(cuts) < count + 1:
        cuts.insert(-1, cuts[-1])
    spans = []
    for index in range(count):
        left = max(start_ms, cuts[index])
        right = cuts[index + 1] if index < count - 1 else end_ms
        right = max(left + 40, right)
        spans.append((left, right))
    spans[-1] = (spans[-1][0], end_ms)
    for index in range(1, count):
        spans[index] = (max(spans[index][0], spans[index - 1][1]), spans[index][1])
        if spans[index][1] <= spans[index][0]:
            spans[index] = (spans[index][0], spans[index][0] + 40)
    spans[-1] = (min(spans[-1][0], end_ms - 40), end_ms)
    return spans


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
        extra = longer[len(shorter):]
        if longer.startswith(shorter) and extra in {"d", "ed", "ing", "s"}:
            return True
    return False


def _asr_window(asr_words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
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
    window = [word for word in _asr_window(asr_words, start_ms, end_ms) if _norm_word(str(word.get("text") or ""))]
    if not window:
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
    if matched < max(2, int(len(pieces) * 0.55)):
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
            chars.append((char, int(left + index * unit), int(left + (index + 1) * unit)))
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
    compact = "".join(char for char in folded if not char.isspace() and char not in ".,!?;:·・。、\"'()[]")
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


def estimate_lrc_offset(lines: list[dict[str, Any]], phrases: list[tuple[int, int]]) -> int:
    """Shift official LRC only when the first vocal is clearly elsewhere."""
    timed = [item for item in lines if item.get("ms") is not None]
    if not timed or not phrases:
        return 0
    raw = phrases[0][0] - int(timed[0]["ms"])
    if abs(raw) < 1500:
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


def snap_unmatched_to_voice(
    bounds: list[dict[str, Any]],
    regions: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    """If an official fallback sits in a hole, slide it onto the vocal before the next ASR line."""
    if not bounds or not regions:
        return bounds
    for index, row in enumerate(bounds[:-1]):
        nxt = bounds[index + 1]
        if row.get("from_asr") or not nxt.get("from_asr"):
            continue
        start_ms = int(row["start_ms"])
        next_start = int(nxt["start_ms"])
        if _voice_covers(regions, start_ms):
            continue
        onsets = [
            region_start
            for region_start, region_end in regions
            if start_ms < region_start < next_start - 250 and region_end - region_start >= 280
        ]
        if not onsets:
            continue
        onset = onsets[0]
        if onset - start_ms < 400 or onset - start_ms > 8000:
            continue
        row["start_ms"] = onset
        row["end_ms"] = max(onset + MIN_LINE_MS, min(int(row["end_ms"]) + (onset - start_ms), next_start))
    return bounds


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
    time_limit = latest if latest is not None else int(asr_words[cursor]["start_ms"]) + 30000
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


def _fallback_line_bounds(
    line: dict[str, Any],
    known_n: int,
    shift: int,
    prev_end: int,
) -> tuple[int, int]:
    if line.get("ms") is not None:
        start_ms = int(line["ms"]) + shift
    else:
        start_ms = prev_end
    if line.get("end_ms") is not None:
        end_ms = int(line["end_ms"]) + shift
    else:
        end_ms = start_ms + max(MIN_LINE_MS, min(MAX_LINE_MS, 180 * known_n))
    return start_ms, max(start_ms + MIN_LINE_MS, end_ms)


def _voice_covers(
    regions: list[tuple[int, int]],
    target_ms: int,
    slop_ms: int = 400,
) -> bool:
    return any(start - slop_ms <= target_ms <= end + slop_ms for start, end in regions)


def _append_bound(
    bounds: list[dict[str, Any]],
    text: str,
    start_ms: int,
    end_ms: int,
    from_asr: bool = False,
) -> None:
    if bounds:
        prev = bounds[-1]
        if start_ms < prev["end_ms"]:
            if prev.get("from_asr") and not from_asr:
                start_ms = int(prev["end_ms"])
            else:
                prev["end_ms"] = max(prev["start_ms"] + MIN_LINE_MS, start_ms)
                start_ms = max(start_ms, prev["end_ms"])
    start_ms = max(0, start_ms)
    end_ms = max(start_ms + MIN_LINE_MS, end_ms)
    bounds.append({"text": text, "start_ms": start_ms, "end_ms": end_ms, "from_asr": from_asr})


def align_lines_to_asr(
    lines: list[dict[str, Any]],
    asr_words: list[dict[str, Any]],
    language: str,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
) -> list[dict[str, Any]]:
    """Walk ASR left-to-right so repeated chorus lines get later spans."""
    asr_words = _usable_asr_words(asr_words)
    if not asr_words:
        return []
    lines = drop_credit_lines(lines, language)
    cursor = 0
    bounds: list[dict[str, Any]] = []
    texts = [str(item.get("text") or "") for item in asr_words]
    accept = accept_score(language)
    shift = estimate_asr_offset(lines, asr_words, language)
    local_shift = shift
    regions = vocal_regions(envelope or [], hop_ms) if envelope else []
    for line in lines:
        raw_text = str(line.get("text") or "")
        known = normalize_lyric(raw_text, language)
        if not known:
            continue
        known_n = len(known.split()) if language == "en" else max(1, len(known))
        official_ms = int(line["ms"]) if line.get("ms") is not None else None
        expected_ms = official_ms + shift if official_ms is not None else None
        earliest = None if expected_ms is None else expected_ms - ASR_WINDOW_BEFORE
        latest = None if expected_ms is None else expected_ms + ASR_WINDOW_AFTER
        # After an ASR hit, later official stamps may have drifted by the same gap.
        if official_ms is not None and bounds and bounds[-1].get("from_asr"):
            drifted = official_ms + local_shift
            earliest = min(earliest or drifted, drifted - ASR_WINDOW_BEFORE)
            latest = max(latest or drifted, drifted + ASR_WINDOW_AFTER)
        match = _best_asr_window(
            known,
            asr_words,
            texts,
            language,
            cursor,
            earliest,
            latest,
            accept,
        )
        # First sung line, or a 0:00 title copy, may start earlier than the stamp.
        if not match and expected_ms is not None and (
            not bounds
            or (
                bounds[-1]["text"] == raw_text
                and int(bounds[-1]["start_ms"]) < 3000
            )
        ):
            match = _best_asr_window(
                known,
                asr_words,
                texts,
                language,
                cursor,
                0,
                expected_ms + ASR_WINDOW_AFTER,
                accept,
            )
        official_alive = official_ms is not None and _voice_covers(regions, official_ms)
        # Official LRC in a hole (wrong stamp / long instrumental): look further.
        # Skip 0:00 title rows so a later sung copy cannot pull the clock.
        if (
            not match
            and expected_ms is not None
            and official_ms is not None
            and official_ms >= 1000
            and not official_alive
        ):
            match = _best_asr_window(
                known,
                asr_words,
                texts,
                language,
                cursor,
                None if earliest is None else min(earliest, expected_ms - ASR_WINDOW_BEFORE),
                expected_ms + ASR_RESCUE_AFTER,
                accept,
            )
        asr_start = int(asr_words[match[1]]["start_ms"]) if match else None
        asr_in_hole = asr_start is not None and not _voice_covers(regions, asr_start)
        prefer_official = (
            match is not None
            and official_ms is not None
            and official_alive
            and asr_start is not None
            and (
                not bounds
                or official_ms + 200 >= int(bounds[-1]["end_ms"]) - 600
            )
            and (
                asr_start - official_ms > LATE_ASR_SLACK_MS
                or (official_ms - asr_start > EARLY_ASR_SLACK_MS and asr_in_hole)
            )
        )
        if match and not prefer_official:
            start_ms = int(asr_words[match[1]]["start_ms"])
            end_ms = int(asr_words[match[2] - 1]["end_ms"])
            cursor = match[2]
            local_shift = start_ms - official_ms if official_ms is not None else local_shift
        else:
            if match and prefer_official:
                cursor = match[2]
                local_shift = shift
            start_ms, end_ms = _fallback_line_bounds(
                line,
                known_n,
                0 if prefer_official else local_shift,
                bounds[-1]["end_ms"] if bounds else 0,
            )
            match = None
        _append_bound(bounds, raw_text, start_ms, end_ms, from_asr=bool(match))
    snap_unmatched_to_voice(bounds, regions)
    restore_short_official_gaps(bounds, lines, shift)
    if bounds and asr_words:
        last_asr = int(asr_words[-1]["end_ms"])
        last = bounds[-1]
        if last_asr > int(last["end_ms"]) and int(last["end_ms"]) - int(last["start_ms"]) < 2500:
            last["end_ms"] = min(last_asr, int(last["start_ms"]) + MAX_LINE_MS)
    return hold_lines_until_next(bounds)


def restore_short_official_gaps(
    bounds: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    shift: int,
) -> list[dict[str, Any]]:
    """Keep short chorus tags from being crushed below the official LRC gap."""
    official_times: dict[str, list[int]] = {}
    for line in lines:
        if line.get("ms") is None:
            continue
        official_times.setdefault(str(line.get("text") or ""), []).append(int(line["ms"]) + shift)
    used: dict[str, int] = {}
    for index, row in enumerate(bounds[:-1]):
        text = str(row.get("text") or "")
        nth = used.get(text, 0)
        used[text] = nth + 1
        times = official_times.get(text) or []
        if nth >= len(times):
            continue
        nxt = bounds[index + 1]
        nxt_text = str(nxt.get("text") or "")
        nxt_times = official_times.get(nxt_text) or []
        nxt_nth = used.get(nxt_text, 0)
        if nxt_nth >= len(nxt_times):
            continue
        official_gap = nxt_times[nxt_nth] - times[nth]
        if official_gap < 500 or int(row["end_ms"]) - int(row["start_ms"]) >= 800:
            continue
        new_end = min(nxt_times[nxt_nth], int(row["start_ms"]) + official_gap)
        if new_end <= int(row["end_ms"]):
            continue
        row["end_ms"] = new_end
        nxt["start_ms"] = max(int(nxt["start_ms"]), new_end)
        nxt["end_ms"] = max(int(nxt["end_ms"]), nxt["start_ms"] + MIN_LINE_MS)
    return bounds


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
            heard = " ".join(texts[start:end]) if language == "en" else "".join(texts[start:end])
            score = match_score(line, heard, language)
            if best is None or score > best[0]:
                best = (score, start, end)
    if best is None or best[0] < match_threshold(language):
        return None
    _, start, end = best
    return int(asr_words[start]["start_ms"]), int(asr_words[end - 1]["end_ms"])


def assign_plain_lines(
    texts: list[str],
    regions: list[tuple[int, int]],
    duration_ms: int,
) -> list[dict[str, Any]]:
    if not texts:
        return []
    slots = list(regions)
    if not slots:
        unit = max(duration_ms, len(texts) * 1000) / len(texts)
        return [{"ms": int(index * unit), "text": text, "end_ms": int((index + 1) * unit)} for index, text in enumerate(texts)]
    while len(slots) < len(texts):
        idx = max(range(len(slots)), key=lambda i: slots[i][1] - slots[i][0])
        start_ms, end_ms = slots[idx]
        mid = (start_ms + end_ms) // 2
        slots[idx : idx + 1] = [(start_ms, mid), (mid, end_ms)]
    while len(slots) > len(texts):
        start_ms, _ = slots[-2]
        _, end_ms = slots[-1]
        slots[-2:] = [(start_ms, end_ms)]
    return [
        {"ms": start_ms, "text": text, "end_ms": end_ms}
        for text, (start_ms, end_ms) in zip(texts, slots)
    ]


def hold_lines_until_next(
    bounds: list[dict[str, Any]],
    max_gap_ms: int = HOLD_GAP_MS,
) -> list[dict[str, Any]]:
    """Keep a line on screen through a short breath, not a long instrumental."""
    for index, row in enumerate(bounds[:-1]):
        nxt = int(bounds[index + 1]["start_ms"])
        end = int(row["end_ms"])
        if 0 < nxt - end <= max_gap_ms:
            row["end_ms"] = nxt
    return bounds


def _vocal_end_near(start_ms: int, regions: list[tuple[int, int]], limit_ms: int = MAX_LINE_MS) -> int:
    """End the line at the vocal burst covering this LRC start, not the next verse."""
    end_ms = start_ms + 4000
    for region_start, region_end in regions:
        if region_end <= start_ms:
            continue
        if region_start > start_ms + 1200:
            break
        end_ms = max(end_ms, min(region_end + 160, start_ms + limit_ms))
    return min(end_ms, start_ms + limit_ms)


def _finalize_line_bounds(
    lines: list[dict[str, Any]],
    regions: list[tuple[int, int]],
    duration_ms: int,
) -> list[dict[str, Any]]:
    """Keep official LRC starts. Voice only trims long instrumental gaps."""
    starts: list[int] = []
    for line in lines:
        raw = line.get("ms")
        starts.append(int(raw) if raw is not None else max(0, int(line.get("end_ms") or 1000) - 1000))
    for index in range(1, len(starts)):
        starts[index] = max(starts[index], starts[index - 1] + 80)
    bounds: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        start_ms = max(0, starts[index])
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        explicit = line.get("end_ms")
        if explicit is not None:
            end_ms = int(explicit)
        elif next_start is not None and next_start - start_ms <= MAX_LINE_MS:
            end_ms = next_start
        else:
            end_ms = _vocal_end_near(start_ms, regions)
            if next_start is not None:
                end_ms = min(end_ms, next_start)
        end_ms = max(start_ms + 200, end_ms)
        if next_start is not None and next_start - start_ms > MAX_LINE_MS:
            end_ms = min(end_ms, start_ms + MAX_LINE_MS)
        elif duration_ms and next_start is None:
            end_ms = min(end_ms, start_ms + MAX_LINE_MS, duration_ms)
        bounds.append({"text": line["text"], "start_ms": start_ms, "end_ms": end_ms})
    return hold_lines_until_next(bounds)


def align_lyrics(
    lines: list[dict[str, Any]],
    language: str | None = None,
    audio_path: Path | None = None,
    duration_ms: int | None = None,
    envelope: list[float] | None = None,
    hop_ms: int = HOP_MS,
    asr_words: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return karaoke timeline anchored to voice when possible."""
    joined = "".join(str(item.get("text") or "") for item in lines)
    lang = detect_language(joined, language)
    lines = prepare_lyric_lines(lines, lang)
    timed = [item for item in lines if item.get("ms") is not None]
    plain = [str(item.get("text") or "") for item in lines if item.get("ms") is None]

    if envelope is None and audio_path is not None:
        envelope, hop_ms = extract_envelope(audio_path, hop_ms)
        duration_ms = duration_ms or probe_duration_ms(audio_path)

    if not lines:
        return {
            "language": lang,
            "alignment": "empty",
            "alignment_source": "",
            "cues": [],
        }

    if asr_words:
        from lovktv.pipeline.lyric_anchor import align_lines_with_anchor

        bounds = align_lines_with_anchor(lines, asr_words, lang, envelope=envelope, hop_ms=hop_ms)
        cues = []
        for row in bounds:
            pieces = tokenize(str(row["text"]), lang)
            spans = asr_token_spans(pieces, row["start_ms"], row["end_ms"], asr_words, lang)
            if not spans:
                spans = energy_token_spans(row["start_ms"], row["end_ms"], len(pieces), envelope or [], hop_ms)
            cue = build_cue(str(row["text"]), row["start_ms"], row["end_ms"], lang, spans)
            if cue:
                cues.append(cue)
        return {
            "language": lang,
            "alignment": "asr",
            "alignment_source": "whisper",
            "cues": cues,
        }

    if envelope:
        regions = vocal_regions(envelope, hop_ms)
        phrases = vocal_phrases(regions)
        if plain and not timed:
            duration = duration_ms or 60_000
            work = assign_plain_lines(plain, phrases or regions, duration)
        elif timed:
            shift = estimate_lrc_offset(timed, phrases)
            shifted = []
            for item in timed:
                row = dict(item)
                row["ms"] = int(item["ms"]) + shift
                if item.get("end_ms") is not None:
                    row["end_ms"] = int(item["end_ms"]) + shift
                shifted.append(row)
            work = shifted
        duration = duration_ms or (int(work[-1]["ms"]) + 4000 if work else 0)
        bounds = _finalize_line_bounds(work, phrases or regions, duration)
        cues = []
        for row in bounds:
            pieces = tokenize(str(row["text"]), lang)
            spans = energy_token_spans(row["start_ms"], row["end_ms"], len(pieces), envelope, hop_ms)
            cue = build_cue(str(row["text"]), row["start_ms"], row["end_ms"], lang, spans)
            if cue:
                cues.append(cue)
        source = str(audio_path.name) if audio_path else "envelope"
        return {
            "language": lang,
            "alignment": "onset",
            "alignment_source": source,
            "cues": cues,
        }

    if timed and all(item.get("ms") is not None for item in lines):
        timeline = timeline_from_lrc(lines, lang, duration_ms=duration_ms)
        timeline["alignment"] = "lrc-interp"
        timeline["alignment_source"] = ""
        return timeline

    duration = duration_ms or max(len(lines) * 4000, 4000)
    texts = [str(item.get("text") or "") for item in lines if item.get("text")]
    assigned = assign_plain_lines(texts, [], duration)
    timeline = timeline_from_lrc(assigned, lang, duration_ms=duration)
    timeline["alignment"] = "duration-fallback"
    timeline["alignment_source"] = ""
    return timeline
