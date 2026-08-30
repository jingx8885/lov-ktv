"""ASR via Whisper CLI or the bundled no-Torch faster-whisper runtime."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from lovktv.core.config import WHISPER_DIR
from lovktv.pipeline.language import whisper_language

WHISPER_BIN = shutil.which("whisper")


@lru_cache(maxsize=2)
def _faster_whisper_model(model_name: str, model_dir: str):
    """Load the optional no-Torch Whisper runtime lazily and reuse it per model."""
    try:
        from faster_whisper import WhisperModel

        return WhisperModel(
            model_name,
            device="cpu",
            compute_type=os.environ.get("LOVKTV_WHISPER_COMPUTE_TYPE", "int8"),
            download_root=model_dir,
        )
    except Exception:  # noqa: BLE001
        return None


def _transcribe_faster_whisper(
    audio_path: Path,
    language: str,
    cache_path: Path | None,
    prompt: str,
) -> list[dict[str, Any]]:
    model_name = (os.environ.get("LOVKTV_WHISPER_MODEL") or "small").strip()
    model_dir = str(Path(os.environ.get("LOVKTV_WHISPER_DIR") or WHISPER_DIR))
    model = _faster_whisper_model(model_name, model_dir)
    if model is None:
        return []
    try:
        segments, _info = model.transcribe(
            str(audio_path),
            language=language,
            task="transcribe",
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=False,
            beam_size=1,
            initial_prompt=prompt.strip()[:400] if prompt.strip() else None,
        )
        payload_segments: list[dict[str, Any]] = []
        for segment in segments:
            words = [
                {
                    "word": str(word.word or "").strip(),
                    "start": float(word.start),
                    "end": float(word.end),
                }
                for word in (segment.words or [])
                if str(word.word or "").strip()
            ]
            payload_segments.append(
                {
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": str(segment.text or "").strip(),
                    "words": words,
                }
            )
        payload = {"segments": payload_segments}
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return _parse_whisper_payload(payload)
    except Exception:  # noqa: BLE001
        return []


def _whisper_pids(needle: str | None = None) -> list[int]:
    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        if "whisper" not in line:
            continue
        if needle is not None and needle not in line:
            continue
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            pids.append(int(parts[0]))
        except ValueError:
            continue
    return pids


def whisper_pids_for(audio_path: Path) -> list[int]:
    """PIDs of whisper CLI already working on this file. Empty if none."""
    return _whisper_pids(str(audio_path))


def any_whisper_pids() -> list[int]:
    return _whisper_pids()


def _wait_until_whisper_idle(timeout: float = 900) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and any_whisper_pids():
        time.sleep(2)


def _copy_cache(sibling: Path, cache_path: Path | None) -> list[dict[str, Any]]:
    words = _parse_whisper_json(sibling)
    if words and cache_path:
        cache_path.write_text(sibling.read_text(encoding="utf-8"), encoding="utf-8")
    return words


def _wait_for_whisper_result(
    audio_path: Path,
    sibling: Path,
    cache_path: Path | None,
    timeout: float = 900,
) -> list[dict[str, Any]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sibling.exists():
            words = _copy_cache(sibling, cache_path)
            if words:
                return words
        if not whisper_pids_for(audio_path):
            break
        time.sleep(2)
    if sibling.exists():
        return _copy_cache(sibling, cache_path)
    return []


def transcribe_words(
    audio_path: Path,
    language: str,
    cache_path: Path | None = None,
    prompt: str = "",
    model: str = "small",
) -> list[dict[str, Any]]:
    """Return word/segment timestamps. Empty if whisper is missing or fails."""
    if cache_path and cache_path.exists():
        cached = _parse_whisper_json(cache_path)
        if cached:
            return cached
    sibling = (
        (cache_path.parent if cache_path else audio_path.parent)
        / "_asr"
        / f"{audio_path.stem}.json"
    )
    if sibling.exists():
        cached = _parse_whisper_json(sibling)
        if cached:
            if cache_path:
                cache_path.write_text(
                    sibling.read_text(encoding="utf-8"), encoding="utf-8"
                )
            return cached
    if whisper_pids_for(audio_path):
        waited = _wait_for_whisper_result(audio_path, sibling, cache_path)
        if waited:
            return waited
    if any_whisper_pids():
        _wait_until_whisper_idle()
        if sibling.exists():
            cached = _parse_whisper_json(sibling)
            if cached:
                if cache_path:
                    cache_path.write_text(
                        sibling.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                return cached
        if whisper_pids_for(audio_path):
            waited = _wait_for_whisper_result(audio_path, sibling, cache_path)
            if waited:
                return waited
    if not audio_path.exists():
        return []

    out_dir = sibling.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if whisper_pids_for(audio_path) or any_whisper_pids():
        if whisper_pids_for(audio_path):
            return _wait_for_whisper_result(audio_path, sibling, cache_path)
        _wait_until_whisper_idle()
        if sibling.exists():
            cached = _copy_cache(sibling, cache_path)
            if cached:
                return cached
    if WHISPER_BIN is None:
        return _transcribe_faster_whisper(audio_path, whisper_language(language), cache_path, prompt)

    cmd = [
        WHISPER_BIN or "whisper",
        str(audio_path),
        "--model",
        model,
        "--language",
        whisper_language(language),
        "--task",
        "transcribe",
        "--word_timestamps",
        "True",
        "--condition_on_previous_text",
        "False",
        "--output_format",
        "json",
        "--output_dir",
        str(out_dir),
        "--verbose",
        "False",
        "--model_dir",
        str(os.environ.get("LOVKTV_WHISPER_DIR") or WHISPER_DIR),
    ]
    if prompt.strip():
        cmd.extend(["--initial_prompt", prompt.strip()[:400]])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=900, check=False
        )
    except OSError:
        return []
    produced = out_dir / f"{audio_path.stem}.json"
    if result.returncode != 0 or not produced.exists():
        return []
    if cache_path:
        cache_path.write_text(produced.read_text(encoding="utf-8"), encoding="utf-8")
        return _parse_whisper_json(cache_path)
    return _parse_whisper_json(produced)


def _parse_whisper_json(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return _parse_whisper_payload(data)


def _parse_whisper_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for seg_i, segment in enumerate(data.get("segments") or []):
        seg_text = str(segment.get("text") or "").strip()
        seg_start = int(float(segment.get("start") or 0) * 1000)
        seg_end = int(float(segment.get("end") or 0) * 1000)
        items = segment.get("words") or []
        parsed: list[dict[str, Any]] = []
        for item in items:
            text = str(item.get("word") or item.get("text") or "").strip()
            if not text:
                continue
            parsed.append(
                {
                    "text": text,
                    "start_ms": int(float(item.get("start") or 0) * 1000),
                    "end_ms": int(float(item.get("end") or 0) * 1000),
                    "segment": seg_i,
                }
            )
        usable_text = "".join(
            item["text"]
            for item in parsed
            if int(item["end_ms"]) - int(item["start_ms"]) >= 40
        )
        compact = seg_text.replace(" ", "")
        if parsed and len(usable_text) >= max(4, len(compact) // 2):
            words.extend(parsed)
            continue
        if compact:
            words.append(
                {
                    "text": seg_text,
                    "start_ms": seg_start,
                    "end_ms": max(seg_end, seg_start + 40),
                    "segment": seg_i,
                }
            )
    return words
