"""ASR via Whisper CLI or the bundled no-Torch faster-whisper runtime."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import wave
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from lovktv.core.config import WHISPER_DIR
from lovktv.pipeline.language import whisper_language

WHISPER_BIN = shutil.which("whisper")
_FISH_MODEL = "fish-transcribe-1"
_GROK_MODEL = "grok-stt"


def _grok_debug_enabled() -> bool:
    """Whether to persist non-secret Grok request/response diagnostics."""
    try:
        from lovktv.storage import settings

        return bool(settings.get("asr_debug"))
    except Exception:  # noqa: BLE001 - diagnostics must never break ASR
        return str(os.environ.get("LOVKTV_ASR_DEBUG") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def _new_grok_debug_trace(cache_path: Path | None, audio_path: Path, language: str) -> tuple[dict[str, Any], Path] | None:
    if not _grok_debug_enabled():
        return None
    directory = (cache_path.parent if cache_path else audio_path.parent) / "_asr-debug"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = f"{time.strftime('%Y%m%dT%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}"
        path = directory / f"grok-{stamp}.json"
        trace: dict[str, Any] = {
            "schema": "lovktv-grok-debug-v1",
            "provider": _GROK_MODEL,
            "language": language,
            "audio": audio_path.name,
            "started_at": time.time(),
            "chunks": [],
            "status": "running",
        }
        return trace, path
    except OSError:
        return None


def _write_grok_debug_trace(trace: dict[str, Any], path: Path) -> None:
    """Best-effort atomic-ish debug write; tracing must not fail transcription."""
    try:
        payload = json.dumps(trace, ensure_ascii=False, indent=2, default=str)
        path.write_text(payload, encoding="utf-8")
        latest = path.parent / "latest.json"
        latest.write_text(payload, encoding="utf-8")
    except (OSError, TypeError, ValueError):
        pass


def _remote_asr_model() -> str:
    """Return the explicitly configured remote ASR model, if any."""
    from lovktv.storage import settings

    configured = str(settings.get("asr_model") or "").strip()
    if not configured:
        configured = str(os.environ.get("LOVKTV_ASR_MODEL") or "").strip()
    return configured


def _cache_matches_model(path: Path, remote_model: str) -> bool:
    """Do not reuse a cache produced by a different ASR backend."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    provider = str(data.get("provider") or "").strip().lower()
    if remote_model not in {_FISH_MODEL, _GROK_MODEL}:
        # Legacy local Whisper caches have no provider marker; remote caches do.
        return provider not in {"fish-audio", "grok-stt"}
    expected = "fish-audio" if remote_model == _FISH_MODEL else "grok-stt"
    return provider == expected


def _remote_asr_endpoint() -> tuple[str, str] | None:
    from lovktv.storage import settings

    base = str(settings.get("agent_url") or os.environ.get("LOVKTV_AGENT_URL") or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
    key = str(settings.get("agent_key") or os.environ.get("LOVKTV_AGENT_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not base or not key:
        return None
    if not base.endswith("/v1"):
        base += "/v1"
    return f"{base}/audio/transcriptions", key


def _fish_tokens(text: str) -> list[str]:
    # Fish currently returns segment timestamps rather than word timestamps.
    # Split CJK per character and Latin text per word so the existing lyric
    # matcher can still use a useful (interpolated) clock.
    return re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?|[\u3400-\u9fff\uf900-\ufaff]|[^\s]", text)


def _parse_fish_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for seg_i, segment in enumerate(data.get("segments") or []):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = float(segment.get("start") or 0)
        end = max(float(segment.get("end") or start), start + 0.04)
        native_words = segment.get("words") or []
        if native_words:
            for item in native_words:
                token = str(item.get("word") or item.get("text") or "").strip()
                if not token:
                    continue
                token_start = float(item.get("start") or start)
                token_end = max(float(item.get("end") or token_start), token_start + 0.04)
                words.append({
                    "text": token,
                    "start_ms": int(round(token_start * 1000)),
                    "end_ms": int(round(token_end * 1000)),
                    "segment": seg_i,
                })
            if words and words[-1]["segment"] == seg_i:
                continue
        tokens = _fish_tokens(text) or [text]
        weights = [max(1, len(token)) for token in tokens]
        total = float(sum(weights))
        cursor = start
        for token, weight in zip(tokens, weights):
            token_end = cursor + (end - start) * weight / total
            words.append({
                "text": token,
                "start_ms": int(round(cursor * 1000)),
                "end_ms": max(int(round(token_end * 1000)), int(round(cursor * 1000)) + 40),
                "segment": seg_i,
            })
            cursor = token_end
    return words


def _parse_grok_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Grok verbose_json word timestamps without degrading precision."""
    words: list[dict[str, Any]] = []
    native = data.get("words") or []
    segments = data.get("segments") or []
    for index, item in enumerate(native):
        if not isinstance(item, dict):
            continue
        text = str(item.get("word") or item.get("text") or "").strip()
        if not text:
            continue
        start = float(item.get("start") or 0)
        end = max(float(item.get("end") or start), start + 0.04)
        segment_value = item.get("segment")
        if segment_value is not None:
            segment = int(segment_value)
        else:
            # verbose_json commonly omits a segment id on each word while
            # still returning segment time ranges.  Recover that grouping so
            # transcript fallback can keep the provider's phrase boundaries.
            segment = index
            for seg_i, seg in enumerate(segments):
                try:
                    seg_start = float(seg.get("start") or 0)
                    seg_end = float(seg.get("end") or seg_start)
                except (TypeError, ValueError):
                    continue
                if seg_start - 0.05 <= start <= seg_end + 0.05:
                    segment = seg_i
                    break
        words.append(
            {
                "text": text,
                "start_ms": int(round(start * 1000)),
                "end_ms": int(round(end * 1000)),
                "segment": segment,
            }
        )
    return words


def _dedupe_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate tokens produced by the intentional chunk overlap."""
    result: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (item.get("start_ms", 0), item.get("end_ms", 0))):
        if result and word.get("text") == result[-1].get("text") and abs(word.get("start_ms", 0) - result[-1].get("start_ms", 0)) <= 180:
            continue
        result.append(word)
    return result


def _audio_duration_seconds(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=20, check=False,
        )
        return max(0.0, float((result.stdout or "").strip()))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def _audio_has_voice(path: Path) -> bool:
    """Cheap gate for chunks that are effectively silent.

    Separation output is normally a PCM WAV.  Use 100 ms RMS windows and keep
    a conservative floor so quiet singing is retained while pure silence (or
    an accidentally empty chunk) never incurs a remote ASR request.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            frames = handle.readframes(handle.getnframes())
        if width != 2 or not frames:
            return True  # unknown encoding: let the provider decide
        import array, math

        pcm = array.array("h")
        pcm.frombytes(frames[: len(frames) - (len(frames) % 2)])
        if channels > 1:
            pcm = array.array("h", (int(sum(pcm[i : i + channels]) / channels) for i in range(0, len(pcm), channels)))
        win = max(1, rate // 10)
        rms_values = [
            math.sqrt(sum(x * x for x in pcm[i : i + win]) / max(1, len(pcm[i : i + win])))
            for i in range(0, len(pcm), win)
        ]
        if not rms_values:
            return False
        return max(rms_values) >= 400.0 and sum(rms_values) / len(rms_values) >= 120.0
    except (OSError, EOFError, ValueError, wave.Error):
        return True


def _remote_chunks(path: Path, audio_format: str = "wav"):
    """Yield (audio path, offset seconds), chunking long songs for remote ASR."""
    duration = _audio_duration_seconds(path)
    if duration <= 35 or not shutil.which("ffmpeg"):
        yield path, 0.0
        return
    with tempfile.TemporaryDirectory(prefix="lovktv-asr-") as folder:
        normalized = Path(folder) / "normalized.wav"
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(normalized)],
            capture_output=True, timeout=180, check=False,
        )
        if result.returncode != 0 or not normalized.exists():
            yield path, 0.0
            return
        # Find low-energy boundaries around each nominal 30s cut.  A 100ms
        # RMS window is enough to avoid splitting a sung syllable while still
        # keeping requests well below the provider's long-audio failure mode.
        with wave.open(str(normalized), "rb") as handle:
            rate = handle.getframerate()
            samples = handle.readframes(handle.getnframes())
        import array, math

        pcm = array.array("h")
        pcm.frombytes(samples[: len(samples) - (len(samples) % 2)])
        win = max(1, rate // 10)
        energy = [
            math.sqrt(sum(x * x for x in pcm[i : i + win]) / max(1, len(pcm[i : i + win])))
            for i in range(0, len(pcm), win)
        ]
        boundaries = [0.0]
        cursor = 30.0
        while cursor < duration - 8.0:
            # Keep a little headroom before the detected minimum: a singer's
            # consonant often starts while RMS is still low, so cutting on
            # the minimum itself can clip the first syllable of the next line.
            lo = max(0, int((cursor - 4.0) * 10))
            hi = min(len(energy), int((cursor + 4.0) * 10))
            # Never let a request exceed the provider's ~35s limit, even when
            # the nearest quiet point is just beyond that limit.
            # Leave room for the 1.5s overlap added when materializing the
            # chunk, keeping the submitted duration safely below 35s.
            hi = min(hi, int((boundaries[-1] + 33.0) * 10))
            if hi > lo:
                cut_i = min(range(lo, hi), key=lambda i: energy[i])
                cut = cut_i / 10.0 - 0.8
                if cut > boundaries[-1] + 8.0:
                    boundaries.append(cut)
            cursor += 30.0
        boundaries.append(duration)
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            # Small overlap protects a syllable that begins just before a
            # quiet boundary.  Returned timestamps are based on this actual
            # start, so the caller can merge them back onto the full track.
            audio_start = max(0.0, start - 1.5) if index else 0.0
            suffix = ".mp3" if audio_format == "mp3" else ".wav"
            chunk = Path(folder) / f"chunk-{index:04d}{suffix}"
            if audio_format == "mp3":
                encode_args = ["-codec:a", "libmp3lame", "-q:a", "2"]
            else:
                encode_args = ["-c:a", "copy"]
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{audio_start:.3f}", "-t", f"{end - audio_start:.3f}", "-i", str(normalized), *encode_args, str(chunk)],
                capture_output=True, timeout=120, check=False,
            )
            if result.returncode == 0 and chunk.exists():
                yield chunk, audio_start


def _transcribe_fish(
    audio_path: Path,
    language: str,
    cache_path: Path | None,
) -> list[dict[str, Any]]:
    endpoint = _remote_asr_endpoint()
    if endpoint is None:
        return []
    url, key = endpoint
    all_words: list[dict[str, Any]] = []
    all_segments: list[dict[str, Any]] = []
    duration = _audio_duration_seconds(audio_path)
    try:
        for chunk, offset in _remote_chunks(audio_path):
            if not _audio_has_voice(chunk):
                continue
            mime = mimetypes.guess_type(chunk.name)[0] or "application/octet-stream"
            with chunk.open("rb") as audio:
                response = httpx.post(url, headers={"Authorization": f"Bearer {key}"}, data={"model": _FISH_MODEL, "language": language, "ignore_timestamps": "false"}, files={"file": (chunk.name, audio, mime)}, timeout=180.0)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                continue
            for segment in payload.get("segments") or []:
                row = dict(segment)
                row["start"] = float(row.get("start") or 0) + offset
                row["end"] = float(row.get("end") or row["start"]) + offset
                if duration > 0:
                    row["start"] = min(row["start"], duration)
                    row["end"] = min(max(row["end"], row["start"]), duration)
                if duration <= 0 or row["start"] <= duration + 0.5:
                    all_segments.append(row)
            for word in _parse_fish_payload(payload):
                word["start_ms"] += int(offset * 1000)
                word["end_ms"] += int(offset * 1000)
                # A few Fish responses contain hallucinated timestamps far
                # beyond the submitted chunk; never let those corrupt the
                # merged timeline.
                if duration > 0:
                    word["end_ms"] = min(word["end_ms"], int(round(duration * 1000)))
                if duration <= 0 or word["start_ms"] / 1000.0 <= duration + 0.5:
                    all_words.append(word)
        all_words = _dedupe_words(all_words)
        if cache_path and all_words:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"duration": _audio_duration_seconds(audio_path), "segments": all_segments, "provider": "fish-audio"}, ensure_ascii=False), encoding="utf-8")
        return all_words
    except Exception:  # noqa: BLE001 - remote ASR is an optional fallback
        return []


def _transcribe_grok(
    audio_path: Path,
    language: str,
    cache_path: Path | None,
) -> list[dict[str, Any]]:
    endpoint = _remote_asr_endpoint()
    if endpoint is None:
        return []
    url, key = endpoint
    debug = _new_grok_debug_trace(cache_path, audio_path, language)
    debug_trace, debug_path = debug or (None, None)

    def persist_debug() -> None:
        if debug_trace is not None and debug_path is not None:
            _write_grok_debug_trace(debug_trace, debug_path)

    data = {
        "model": _GROK_MODEL,
        "language": language,
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word",
    }
    if debug_trace is not None:
        # Keep the exact non-secret form fields alongside each raw response;
        # never include the Authorization header or endpoint key.
        debug_trace["request"] = dict(data)
        persist_debug()
    try:
        all_words: list[dict[str, Any]] = []
        # Grok's upstream decoder is sensitive to isolated PCM WAV sections;
        # MP3 chunks preserve the vocal signal and avoid valid-200/empty
        # responses seen in the latter half of this song.
        for chunk_index, (chunk, offset) in enumerate(
            _remote_chunks(audio_path, audio_format="mp3")
        ):
            if not _audio_has_voice(chunk):
                if debug_trace is not None:
                    debug_trace["chunks"].append(
                        {
                            "index": chunk_index,
                            "offset_seconds": offset,
                            "file": chunk.name,
                            "skipped": "silence",
                        }
                    )
                    persist_debug()
                continue

            chunk_debug: dict[str, Any] = {
                "index": chunk_index,
                "offset_seconds": offset,
                "file": chunk.name,
                "attempts": [],
            }
            if debug_trace is not None:
                debug_trace["chunks"].append(chunk_debug)

            def request_chunk(request_path: Path, phase: str) -> list[dict[str, Any]]:
                words: list[dict[str, Any]] = []
                # Keep the initial request plus three retries.  Empty 200
                # responses are treated like transient upstream failures.
                for attempt in range(4):
                    attempt_debug: dict[str, Any] = {
                        "phase": phase,
                        "attempt": attempt + 1,
                        "file": request_path.name,
                    }
                    if debug_trace is not None:
                        chunk_debug["attempts"].append(attempt_debug)
                    try:
                        mime = mimetypes.guess_type(request_path.name)[0] or "application/octet-stream"
                        attempt_debug["mime"] = mime
                        with request_path.open("rb") as audio:
                            response = httpx.post(
                                url,
                                headers={"Authorization": f"Bearer {key}"},
                                data=data,
                                files={"file": (request_path.name, audio, mime)},
                                timeout=180.0,
                            )
                        attempt_debug["status_code"] = getattr(response, "status_code", None)
                        response.raise_for_status()
                        payload = response.json()
                        if debug_trace is not None:
                            attempt_debug["response"] = payload
                        if isinstance(payload, dict):
                            words = _parse_grok_payload(payload)
                        attempt_debug["parsed_words"] = len(words)
                        if words:
                            attempt_debug["result"] = "ok"
                            persist_debug()
                            return words
                        attempt_debug["result"] = "empty"
                    except Exception as exc:  # noqa: BLE001 - retry transient upstream failures
                        attempt_debug["error"] = f"{type(exc).__name__}: {exc}"
                    persist_debug()
                    if attempt < 3:
                        time.sleep(0.5)
                return words

            chunk_words = request_chunk(chunk, "mp3")
            if not chunk_words:
                # Some upstream paths reject MP3 frames while accepting the
                # equivalent PCM WAV.  Re-encode only this failed slice so
                # successful MP3 chunks keep the fast path.
                wav_chunk = chunk.with_suffix(".wav")
                try:
                    converted = subprocess.run(
                        [
                            "ffmpeg", "-y", "-loglevel", "error", "-i", str(chunk),
                            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_chunk),
                        ],
                        capture_output=True,
                        timeout=120,
                        check=False,
                    )
                    if converted.returncode == 0 and wav_chunk.exists():
                        chunk_debug["wav_reencode"] = "ok"
                        chunk_words = request_chunk(wav_chunk, "wav")
                    elif debug_trace is not None:
                        chunk_debug["wav_reencode"] = "failed"
                except (OSError, subprocess.TimeoutExpired) as exc:
                    if debug_trace is not None:
                        chunk_debug["wav_reencode"] = f"error: {type(exc).__name__}: {exc}"
                persist_debug()
            if not chunk_words:
                # Grok occasionally returns a valid 200 with an empty body for
                # sung material.  Keep the configured Grok-first path, but
                # recover only this failed slice with the local no-Torch
                # Whisper runtime instead of losing the whole song.
                chunk_debug["fallback"] = "faster-whisper"
                chunk_words = _transcribe_faster_whisper(chunk, language, None, "")
                chunk_debug["fallback_words"] = len(chunk_words)
                persist_debug()
            for word in chunk_words:
                word["start_ms"] += int(offset * 1000)
                word["end_ms"] += int(offset * 1000)
                all_words.append(word)
        all_words = _dedupe_words(all_words)
        if cache_path and all_words:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"words": [{"text": w["text"], "start": w["start_ms"] / 1000, "end": w["end_ms"] / 1000, "segment": w.get("segment")} for w in all_words], "provider": "grok-stt", "duration": _audio_duration_seconds(audio_path)}, ensure_ascii=False), encoding="utf-8")
        if debug_trace is not None:
            debug_trace["status"] = "ok"
            debug_trace["word_count"] = len(all_words)
            debug_trace["finished_at"] = time.time()
            persist_debug()
        return all_words
    except Exception as exc:  # noqa: BLE001 - remote ASR is an optional fallback
        if debug_trace is not None:
            debug_trace["status"] = "error"
            debug_trace["error"] = f"{type(exc).__name__}: {exc}"
            debug_trace["finished_at"] = time.time()
            persist_debug()
        return []


@lru_cache(maxsize=2)
def _faster_whisper_model(model_name: str, model_dir: str):
    """Load the optional no-Torch Whisper runtime lazily and reuse it per model."""
    try:
        from faster_whisper import WhisperModel

        from lovktv.storage import settings

        return WhisperModel(
            model_name,
            device="cpu",
            compute_type=settings.get("whisper_compute_type"),
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
    from lovktv.storage import settings

    model_name = settings.get("whisper_model")
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
    remote_model = _remote_asr_model().lower()
    if cache_path and cache_path.exists() and _cache_matches_model(cache_path, remote_model):
        cached = _parse_whisper_json(cache_path)
        if cached:
            return cached
    sibling = (
        (cache_path.parent if cache_path else audio_path.parent)
        / "_asr"
        / f"{audio_path.stem}.json"
    )
    if sibling.exists() and _cache_matches_model(sibling, remote_model):
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

    # Remote Fish ASR is opt-in.  Keep local Whisper as the normal path and as
    # a fallback when the gateway or upstream model is unavailable.
    if remote_model in {_FISH_MODEL, _GROK_MODEL}:
        remote_fn = _transcribe_fish if remote_model == _FISH_MODEL else _transcribe_grok
        remote = remote_fn(audio_path, whisper_language(language), cache_path)
        if remote:
            return remote

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
    provider = str(data.get("provider") or "").strip().lower()
    if provider == "fish-audio":
        return _parse_fish_payload(data)
    if provider == "grok-stt":
        return _parse_grok_payload(data)
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
