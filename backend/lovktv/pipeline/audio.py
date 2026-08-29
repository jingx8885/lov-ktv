"""Audio probing and vocal envelope utilities."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from lovktv.pipeline.constants import HOP_MS


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
        envelope.append(
            math.sqrt(sum(sample * sample for sample in chunk) / len(chunk))
        )
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
