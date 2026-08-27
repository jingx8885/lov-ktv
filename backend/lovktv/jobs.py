from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from pathlib import Path

from lovktv.agents.ja_lyrics import annotate_ja_lines, apply_ja_annotation
from lovktv.catalog.fetch import import_song, parse_lrc
from lovktv.catalog.mugen import attach_vocal_audio, is_mugen_kid, is_off_vocal
from lovktv.config import MEDIA_DIR
from lovktv.pipeline.align import align_lyrics, extract_envelope, pack_tokens_to_singing, probe_duration_ms
from lovktv.pipeline.language import detect_language
from lovktv.pipeline.lyrics import (
    parse_plain_lines,
    prepare_lyric_lines,
    rebuild_manual_timeline,
    write_manual_lrc,
    write_subtitles,
)
from lovktv.pipeline.mtv import compose_mtv
from lovktv.pipeline.transcribe import transcribe_words
from lovktv.pipeline.separate import named_stem, save_stem_wav, separate_vocals
from lovktv.store import get_song, list_songs, retry_query, update_song


def _publish_ready(song_id: str) -> None:
    try:
        from lovktv.oss import publish_song

        publish_song(song_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[lovktv] oss publish {song_id} skipped: {exc}", flush=True)

_JOBS: queue.Queue = queue.Queue()
_QUEUED: set[str] = set()
_QUEUE_LOCK = threading.Lock()
_WORKER_STARTED = False


def _fallback_media(src: Path, out_dir: Path) -> None:
    import shutil
    import subprocess

    karaoke = out_dir / "karaoke.m4a"
    guide = out_dir / "guide.m4a"
    if shutil.which("ffmpeg"):
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-c:a", "aac", "-b:a", "192k", str(karaoke)],
            check=True,
            timeout=120,
            capture_output=True,
        )
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-c:a", "aac", "-b:a", "64k", str(guide)], check=True, timeout=120, capture_output=True)
    else:
        shutil.copy2(src, out_dir / "karaoke.m4a")
        shutil.copy2(src, out_dir / "guide.m4a")


def _is_mugen_skeleton(skeleton: dict) -> bool:
    source = skeleton.get("source") if isinstance(skeleton.get("source"), dict) else {}
    audio = skeleton.get("audio") if isinstance(skeleton.get("audio"), dict) else {}
    return source.get("provider") == "karaoke-mugen" or str(audio.get("source") or "").startswith("mugen")


def _is_mugen_dual(skeleton: dict) -> bool:
    audio = skeleton.get("audio") if isinstance(skeleton.get("audio"), dict) else {}
    return bool(audio.get("dual_audio")) or audio.get("source") == "mugen-dual"


def ensure_karaoke_stems(out_dir: Path, src: Path, skeleton: dict) -> str:
    """Make 伴奏 karaoke.m4a and 原唱 original.mp3 after a Karaoke Mugen MP4.

    Dual-track files already have both. Off-vocal files keep the official
    karaoke and fetch the vocal sibling. Everything else runs ONNX.
    """
    karaoke = out_dir / "karaoke.m4a"
    original = out_dir / "original.mp3"
    source = skeleton.get("source") if isinstance(skeleton.get("source"), dict) else {}
    if _is_mugen_dual(skeleton):
        if karaoke.exists() and original.exists():
            return "dual"
        _fallback_media(src, out_dir)
        return "dual-fallback"
    off = is_off_vocal(str(source.get("songname") or ""), str(skeleton.get("title") or ""))
    if off:
        if src.exists() and not karaoke.exists():
            _fallback_media(src, out_dir)
        if attach_vocal_audio(out_dir, skeleton) and karaoke.exists() and original.exists():
            return "off-vocal+vocal"
    separate_vocals(original if original.exists() else src, out_dir)
    return "onnx"


def process_import(song_id: str, query: str, netease_id: str = "", language: str | None = None) -> None:
    out_dir = MEDIA_DIR / song_id
    try:
        update_song(song_id, status="fetching")
        skeleton = import_song(query=query, out_dir=out_dir, song_id=netease_id or None)
        lang = str(language or skeleton.get("language") or "")
        fields = {
            "title": skeleton.get("title") or query,
            "audio_source": (skeleton.get("audio") or {}).get("source") or "",
            "status": "separating",
        }
        if skeleton.get("artist"):
            fields["artist"] = str(skeleton["artist"])
        if lang:
            fields["language"] = lang
        mugen_kid = str(netease_id or (skeleton.get("source") or {}).get("kid") or "")
        if is_mugen_kid(mugen_kid):
            fields["netease_id"] = mugen_kid
        update_song(song_id, **fields)
        src = out_dir / "original.mp3"
        if not src.exists():
            raise RuntimeError("音频下载失败，没有 original.mp3")
        if _is_mugen_skeleton(skeleton):
            try:
                ensure_karaoke_stems(out_dir, src, skeleton)
            except Exception as sep_exc:
                update_song(song_id, error=f"分离降级：{sep_exc}")
                _fallback_media(src, out_dir)
        elif skeleton.get("needs_separate", True):
            try:
                separate_vocals(src, out_dir)
            except Exception as sep_exc:
                update_song(song_id, error=f"分离降级：{sep_exc}")
                _fallback_media(src, out_dir)
        elif not (out_dir / "karaoke.m4a").exists():
            _fallback_media(src, out_dir)
        if skeleton.get("needs_align", True) or not (out_dir / "lyrics.json").exists():
            _align_and_mtv(song_id, out_dir, src, lang or language, rebuild_mtv=not skeleton.get("has_video"))
            return
        _finish_ready_lyrics(song_id, out_dir, src, lang or language, rebuild_mtv=not skeleton.get("has_video"))
    except Exception as exc:  # noqa: BLE001 — job must record any failure
        update_song(song_id, status="failed", error=str(exc))


def _finish_ready_lyrics(
    song_id: str,
    out_dir: Path,
    src: Path,
    language: str | None,
    rebuild_mtv: bool = True,
) -> None:
    """Keep Karaoke Mugen (or other pre-timed) lyrics; skip Whisper."""
    import json

    lyrics_path = out_dir / "lyrics.json"
    timeline = json.loads(lyrics_path.read_text(encoding="utf-8"))
    lang = str(timeline.get("language") or language or detect_language(
        "".join(str(cue.get("text") or "") for cue in timeline.get("cues") or [])
    ))
    burned = bool(timeline.get("burned_lyrics"))
    official = not rebuild_mtv and (
        (out_dir / "mugen.mp4").exists()
        or (out_dir / "mugen.webm").exists()
        or str(timeline.get("alignment_source") or "") == "karaoke-mugen"
    )
    if official:
        timeline["native_video"] = True
    if lang == "ja" and not burned:
        update_song(song_id, language=lang, status="annotating")
    else:
        update_song(song_id, language=lang, status="ready")
        _publish_ready(song_id)
    wrote = False
    if lang == "ja" and timeline.get("cues") and not burned:
        song = get_song(song_id) or {}
        try:
            notes = annotate_ja_lines(
                [str(cue.get("text") or "") for cue in timeline["cues"]],
                title=str(song.get("title") or ""),
                artist=str(song.get("artist") or ""),
                cache_path=out_dir / "ja-annotate.json",
            )
            apply_ja_annotation(timeline, notes)
            write_subtitles(timeline, out_dir)
            wrote = True
            previous = str((get_song(song_id) or {}).get("error") or "")
            if "注音降级" in previous:
                update_song(song_id, error="")
        except Exception as ann_exc:
            previous = str((get_song(song_id) or {}).get("error") or "").strip()
            update_song(song_id, error=f"{previous} 注音降级：{ann_exc}".strip())
    if timeline.get("native_video") and not wrote:
        write_subtitles(timeline, out_dir)
    update_song(song_id, status="ready")
    _publish_ready(song_id)
    if not rebuild_mtv and (out_dir / "mtv.mp4").exists():
        return
    song = get_song(song_id) or {}
    audio = out_dir / "karaoke.m4a"
    if not audio.exists():
        audio = src
    cover = out_dir / "cover.jpg"
    try:
        compose_mtv(
            out_dir,
            audio_path=audio,
            title=str(song.get("title") or "lov-ktv"),
            artist=str(song.get("artist") or ""),
            timeline=timeline,
            cover_path=cover if cover.exists() else None,
        )
        _publish_ready(song_id)
    except Exception as mtv_exc:
        previous = str(song.get("error") or "").strip()
        update_song(song_id, error=f"{previous} MTV降级：{mtv_exc}".strip())


def process_upload(song_id: str, src: Path, language: str | None = None) -> None:
    out_dir = MEDIA_DIR / song_id
    try:
        update_song(song_id, status="separating")
        if not src.exists():
            raise RuntimeError("没有上传音频")
        try:
            separate_vocals(src, out_dir)
        except Exception as sep_exc:
            update_song(song_id, error=f"分离降级：{sep_exc}")
            _fallback_media(src, out_dir)
        _align_and_mtv(song_id, out_dir, src, language, rebuild_mtv=True)
    except Exception as exc:  # noqa: BLE001
        update_song(song_id, status="failed", error=str(exc))


def load_lyric_lines(out_dir: Path) -> list[dict]:
    path = out_dir / "lyrics.lrc"
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    lines = parse_lrc(raw) or parse_plain_lines(raw)
    lang = detect_language("".join(item.get("text") or "" for item in lines))
    return prepare_lyric_lines(lines, lang)


def _voice_audio(out_dir: Path, src: Path) -> Path:
    for name in ("vocals.wav", "guide.m4a", "original.mp3"):
        candidate = out_dir / name
        if candidate.exists():
            return candidate
    return src


def _ensure_vocals(out_dir: Path, src: Path) -> Path:
    """Finish a killed vocal split enough for ASR; do not re-run separator."""
    vocals = out_dir / "vocals.wav"
    if vocals.exists():
        return vocals
    leftover = named_stem(out_dir, "Vocals")
    if leftover:
        return save_stem_wav(leftover, vocals)
    if src.exists() and shutil.which("ffmpeg"):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), str(vocals)],
                check=True,
                timeout=180,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return _voice_audio(out_dir, src)
        if vocals.exists():
            return vocals
    return _voice_audio(out_dir, src)


def apply_locked_manual(song_id: str, rebuild_mtv: bool = False) -> None:
    """Rebuild lyrics.json from a frozen manual LRC. Do not run Whisper."""
    import json

    out_dir = MEDIA_DIR / song_id
    raw = (out_dir / "lyrics.manual.lrc").read_text(encoding="utf-8")
    rows = parse_lrc(raw) or parse_plain_lines(raw)
    existing: dict = {}
    lyrics_path = out_dir / "lyrics.json"
    if lyrics_path.exists():
        existing = json.loads(lyrics_path.read_text(encoding="utf-8"))
    lang = detect_language("".join(str(item.get("text") or "") for item in rows), existing.get("language"))
    rows = prepare_lyric_lines(rows, lang)
    src = out_dir / "original.mp3"
    timeline = rebuild_manual_timeline(rows, existing, probe_duration_ms(src) if src.exists() else None)
    notes_path = out_dir / "ja-annotate.json"
    if lang == "ja" and notes_path.exists():
        apply_ja_annotation(timeline, json.loads(notes_path.read_text(encoding="utf-8")))
    voice = out_dir / "vocals.wav"
    if not voice.exists():
        voice = src
    if voice.exists():
        envelope, hop_ms = extract_envelope(voice)
        pack_tokens_to_singing(timeline["cues"], envelope, hop_ms)
    write_subtitles(timeline, out_dir)
    write_manual_lrc(out_dir, timeline["cues"])
    update_song(song_id, language=lang, status="ready")
    _publish_ready(song_id)
    if rebuild_mtv:
        song = get_song(song_id) or {}
        audio = out_dir / "karaoke.m4a"
        if not audio.exists():
            audio = src
        cover = out_dir / "cover.jpg"
        compose_mtv(
            out_dir,
            audio_path=audio,
            title=str(song.get("title") or "lov-ktv"),
            artist=str(song.get("artist") or ""),
            timeline=timeline,
            cover_path=cover if cover.exists() else None,
        )
        _publish_ready(song_id)


def process_realign(song_id: str, language: str | None = None, rebuild_mtv: bool = False) -> None:
    """Re-run the same ASR + lyric pipeline used by import/upload."""
    out_dir = MEDIA_DIR / song_id
    src = out_dir / "original.mp3"
    if not src.exists():
        src = _voice_audio(out_dir, out_dir / "karaoke.m4a")
    try:
        if not src.exists():
            raise RuntimeError("没有可对齐的音频")
        if (out_dir / "lyrics.manual.lrc").exists():
            apply_locked_manual(song_id, rebuild_mtv=rebuild_mtv)
            return
        _align_and_mtv(song_id, out_dir, src, language, rebuild_mtv=rebuild_mtv)
    except Exception as exc:  # noqa: BLE001
        update_song(song_id, status="failed", error=str(exc))


def _align_and_mtv(
    song_id: str,
    out_dir: Path,
    src: Path,
    language: str | None,
    rebuild_mtv: bool = True,
) -> None:
    lines = load_lyric_lines(out_dir)
    lang = detect_language("".join(item.get("text") or "" for item in lines), language)
    update_song(song_id, language=lang, status="aligning")
    voice = _ensure_vocals(out_dir, src)
    prompt = "\n".join(str(item.get("text") or "") for item in lines[:10])
    asr_words = transcribe_words(
        voice,
        lang,
        cache_path=out_dir / "asr.json",
        prompt=prompt,
    )
    timeline = align_lyrics(
        lines,
        lang,
        audio_path=voice,
        duration_ms=probe_duration_ms(src) or probe_duration_ms(voice),
        asr_words=asr_words or None,
    )
    if lang == "ja" and timeline.get("cues"):
        update_song(song_id, status="annotating")
        song = get_song(song_id) or {}
        try:
            notes = annotate_ja_lines(
                [str(cue.get("text") or "") for cue in timeline["cues"]],
                title=str(song.get("title") or ""),
                artist=str(song.get("artist") or ""),
                cache_path=out_dir / "ja-annotate.json",
            )
            apply_ja_annotation(timeline, notes)
            previous = str((get_song(song_id) or {}).get("error") or "")
            if "注音降级" in previous:
                update_song(song_id, error="")
        except Exception as ann_exc:
            previous = str((get_song(song_id) or {}).get("error") or "").strip()
            update_song(song_id, error=f"{previous} 注音降级：{ann_exc}".strip())
    if timeline.get("cues"):
        write_subtitles(timeline, out_dir)
    update_song(song_id, status="ready")
    _publish_ready(song_id)
    if not rebuild_mtv and (out_dir / "mtv.mp4").exists():
        return
    song = get_song(song_id) or {}
    audio = out_dir / "karaoke.m4a"
    if not audio.exists():
        audio = src
    cover = out_dir / "cover.jpg"
    try:
        compose_mtv(
            out_dir,
            audio_path=audio,
            title=str(song.get("title") or "lov-ktv"),
            artist=str(song.get("artist") or ""),
            timeline=timeline,
            cover_path=cover if cover.exists() else None,
        )
        _publish_ready(song_id)
    except Exception as mtv_exc:
        previous = str(song.get("error") or "").strip()
        note = f"MTV降级：{mtv_exc}"
        update_song(song_id, error=f"{previous} {note}".strip())


def _job_key(fn, args: tuple) -> str:
    name = getattr(fn, "__name__", str(fn))
    song_id = args[0] if args else ""
    return f"{name}:{song_id}"


def _worker() -> None:
    while True:
        fn, args, kwargs, key = _JOBS.get()
        try:
            print(f"[lovktv] start {key}", flush=True)
            fn(*args, **kwargs)
            print(f"[lovktv] done {key}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[lovktv] fail {key}: {exc}", flush=True)
        finally:
            with _QUEUE_LOCK:
                _QUEUED.discard(key)
            _JOBS.task_done()


def spawn(fn, *args, **kwargs) -> None:
    """Queue background work. One worker, so Whisper is not stampeded."""
    global _WORKER_STARTED
    key = _job_key(fn, args)
    with _QUEUE_LOCK:
        if key in _QUEUED:
            return
        _QUEUED.add(key)
        if not _WORKER_STARTED:
            _WORKER_STARTED = True
            threading.Thread(target=_worker, name="lovktv-jobs", daemon=True).start()
        _JOBS.put((fn, args, kwargs, key))


def _has_ready_lyrics(out_dir: Path) -> bool:
    path = out_dir / "lyrics.json"
    if not path.exists():
        return False
    try:
        import json

        meta = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    source = str(meta.get("alignment_source") or "")
    return source in {"karaoke-mugen", "kugou"} or meta.get("needs_align") is False


def resume_stuck_jobs() -> int:
    """Continue songs left queued/aligning after a reload killed the worker."""
    resumed = 0
    pending_finish: list[tuple] = []
    pending_align: list[tuple] = []
    pending_import: list[tuple] = []
    for song in reversed(list_songs()):
        status = str(song.get("status") or "")
        song_id = str(song["id"])
        out_dir = MEDIA_DIR / song_id
        has_audio = (out_dir / "original.mp3").exists() or (out_dir / "vocals.wav").exists()
        if status in {"aligning", "annotating", "composing", "separating"} and has_audio:
            if _has_ready_lyrics(out_dir):
                pending_finish.append((song_id, out_dir, song.get("language")))
            else:
                pending_align.append((song_id, song.get("language")))
            continue
        if status in {"queued", "fetching"}:
            pending_import.append(
                (song_id, retry_query(song), str(song.get("netease_id") or ""), song.get("language"))
            )
    for song_id, out_dir, language in pending_finish:
        src = out_dir / "original.mp3"
        if not src.exists():
            src = _voice_audio(out_dir, out_dir / "karaoke.m4a")
        if src.exists() and not (out_dir / "karaoke.m4a").exists():
            try:
                _fallback_media(src, out_dir)
            except Exception:
                pass
        spawn(_finish_ready_lyrics, song_id, out_dir, src, language, False)
        resumed += 1
    for song_id, language in pending_align:
        spawn(process_realign, song_id, language, True)
        resumed += 1
    for song_id, query, netease_id, language in pending_import:
        spawn(process_import, song_id, query, netease_id, language)
        resumed += 1
    if resumed:
        print(f"[lovktv] resume {resumed} stuck songs", flush=True)
    return resumed
