from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Protocol

from lovktv.agents.alignment import align_lines_with_agent
from lovktv.agents.ja_lyrics import (
    annotate_ja_lines,
    apply_ja_annotation,
    line_is_romaji,
    lyric_source_key,
)
from lovktv.agents.translate import (
    TRANSLATE_SCHEMA,
    apply_zh_translation,
    is_chinese_lang,
    translate_lines,
)
from lovktv.catalog.audio import extract_mv_mp3
from lovktv.catalog.bilibili import VIEW_URL, api_get, is_bvid
from lovktv.catalog.kugou import fetch_kugou_lyrics
from lovktv.catalog.importer import import_song
from lovktv.catalog.lyrics import parse_lrc
from lovktv.catalog.mugen import attach_vocal_audio, is_mugen_kid, is_off_vocal, prepare_media
from lovktv.core.config import MEDIA_DIR
from lovktv.pipeline.audio import extract_envelope, probe_duration_ms
from lovktv.pipeline.bounds import pack_tokens_to_singing
from lovktv.pipeline.language import resolve_language
from lovktv.pipeline.lyrics import (
    parse_plain_lines,
    prepare_lyric_lines,
    rebuild_manual_timeline,
    write_manual_lrc,
    write_subtitles,
)
from lovktv.pipeline.mtv import compose_mtv
from lovktv.pipeline.orchestrator import (
    _looks_like_wrong_lyric_version,
    align_lyrics,
)
from lovktv.pipeline.separate import named_stem, save_stem_wav, separate_vocals
from lovktv.pipeline.transcribe import transcribe_words
from lovktv.storage import store as _store
from lovktv.workers import debug as processing_debug
from lovktv.workers.queue import JobQueue, job_queue, spawn

__all__ = [
    "JobQueue",
    "job_queue",
    "spawn",
    "process_import",
    "process_upload",
    "process_realign",
    "resume_stuck_jobs",
]


class SongRepository(Protocol):
    """Persistence boundary for background song processing."""

    def get(self, song_id: str) -> dict | None: ...

    def list(self) -> list[dict]: ...

    def update(self, song_id: str, **fields: Any) -> None: ...

    def retry_query(self, song: dict) -> str: ...


class StoreSongRepository:
    """Adapter for the current store; replaceable in workers and tests."""

    def get(self, song_id: str) -> dict | None:
        return _store.get_song(song_id)

    def list(self) -> list[dict]:
        return _store.list_songs()

    def update(self, song_id: str, **fields: Any) -> None:
        _store.update_song(song_id, **fields)

    def retry_query(self, song: dict) -> str:
        return _store.retry_query(song)


song_repository: SongRepository = StoreSongRepository()


# Compatibility seams for existing callers/tests.  Worker code calls these
# names, while the actual persistence dependency is now injected above.
def get_song(song_id: str) -> dict | None:
    return song_repository.get(song_id)


def list_songs() -> list[dict]:
    return song_repository.list()


def update_song(song_id: str, **fields: Any) -> None:
    song_repository.update(song_id, **fields)


def retry_query(song: dict) -> str:
    return song_repository.retry_query(song)


def _publish_ready(song_id: str) -> None:
    try:
        from lovktv.media.oss import publish_song

        publish_song(song_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[lovktv] oss publish {song_id} skipped: {exc}", flush=True)


JobFn = Callable[..., Any]


def _fallback_media(src: Path, out_dir: Path) -> None:
    import shutil
    import subprocess

    karaoke = out_dir / "karaoke.m4a"
    guide = out_dir / "guide.m4a"
    if shutil.which("ffmpeg"):
        from lovktv.pipeline.loudness import loudnorm_args

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                *loudnorm_args(),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(karaoke),
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                *loudnorm_args(),
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                str(guide),
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )
    else:
        shutil.copy2(src, out_dir / "karaoke.m4a")
        shutil.copy2(src, out_dir / "guide.m4a")


def _is_mugen_skeleton(skeleton: dict) -> bool:
    source = skeleton.get("source") if isinstance(skeleton.get("source"), dict) else {}
    audio = skeleton.get("audio") if isinstance(skeleton.get("audio"), dict) else {}
    return source.get("provider") == "karaoke-mugen" or str(
        audio.get("source") or ""
    ).startswith("mugen")


def _is_mugen_dual(skeleton: dict) -> bool:
    audio = skeleton.get("audio") if isinstance(skeleton.get("audio"), dict) else {}
    return bool(audio.get("dual_audio")) or audio.get("source") == "mugen-dual"


def _is_mugen_off_vocal(skeleton: dict) -> bool:
    source = skeleton.get("source") if isinstance(skeleton.get("source"), dict) else {}
    return _is_mugen_skeleton(skeleton) and is_off_vocal(
        str(source.get("songname") or ""), str(skeleton.get("title") or "")
    )


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
    off = is_off_vocal(
        str(source.get("songname") or ""), str(skeleton.get("title") or "")
    )
    if off:
        if src.exists() and not karaoke.exists():
            _fallback_media(src, out_dir)
        if (
            attach_vocal_audio(out_dir, skeleton)
            and karaoke.exists()
            and original.exists()
        ):
            return "off-vocal+vocal"
    separate_vocals(original if original.exists() else src, out_dir)
    return "onnx"


def _refresh_audio_tracks(out_dir: Path, skeleton: dict) -> Path:
    """Rebuild canonical playback tracks without destroying an original vocal.

    Karaoke Mugen off-vocal entries use the official MV as the backing track
    and a separately linked sibling as the original vocal.  The MV therefore
    must never be used to refresh ``original.mp3`` for those songs.
    """
    source = skeleton.get("source") if isinstance(skeleton.get("source"), dict) else {}
    audio = skeleton.get("audio") if isinstance(skeleton.get("audio"), dict) else {}
    original = out_dir / "original.mp3"
    native_mtv = out_dir / "mtv.mp4"
    mugen_song = source.get("provider") == "karaoke-mugen"
    mugen_off_vocal = _is_mugen_off_vocal(skeleton)

    # Karaoke Mugen dual-track files keep their video without audio. Rebuild
    # the full original by mixing the official instrumental and vocal tracks.
    mugen_src = next(
        (path for path in (out_dir / "mugen.mp4", out_dir / "mugen.webm") if path.exists()),
        None,
    )
    if mugen_off_vocal:
        # ``mtv.mp4`` is the off-vocal media. Restore the linked vocal sibling
        # instead of extracting that accompaniment over the canonical master.
        if not attach_vocal_audio(out_dir, skeleton):
            raise RuntimeError("Mugen 原唱轨恢复失败")
        original = out_dir / "original.mp3"
    elif (
        mugen_src
        and mugen_song
        and (audio.get("dual_audio") or audio.get("source") == "mugen-dual")
    ):
        refreshed = prepare_media(mugen_src, out_dir)
        skeleton["audio"] = {**audio, **refreshed}
        skeleton["has_video"] = bool(refreshed.get("has_video"))
        (out_dir / "skeleton.json").write_text(
            json.dumps(skeleton, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif _has_native_mtv(out_dir) and native_mtv.exists():
        if extract_mv_mp3(native_mtv, original):
            audio["mv_audio_extracted"] = True
            skeleton["audio"] = audio
            (out_dir / "skeleton.json").write_text(
                json.dumps(skeleton, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    if not original.exists():
        raise RuntimeError("MV 原曲提取失败，没有 original.mp3")
    if mugen_off_vocal:
        # The official karaoke.m4a and guide.m4a were already produced from
        # their respective Mugen siblings.  Running ONNX on the vocal master
        # here would turn karaoke back into a near-silent accompaniment.
        return original
    separate_vocals(original, out_dir)
    return original


def process_import(
    song_id: str, query: str, netease_id: str = "", language: str | None = None
) -> None:
    out_dir = MEDIA_DIR / song_id
    processing_debug.start(song_id, "import")
    processing_debug.event(song_id, "queued", query=query, netease_id=netease_id or "")
    try:
        update_song(song_id, status="fetching")
        processing_debug.event(song_id, "fetch", status="running")
        skeleton = import_song(query=query, out_dir=out_dir, song_id=netease_id or None)
        processing_debug.event(song_id, "fetch", files=sorted(path.name for path in out_dir.iterdir()) if out_dir.exists() else [])
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
        processing_debug.event(song_id, "metadata", title=fields.get("title"), language=lang, audio_source=fields.get("audio_source"))
        src = out_dir / "original.mp3"
        if not src.exists():
            raise RuntimeError("音频下载失败，没有 original.mp3")
        if _is_mugen_skeleton(skeleton):
            try:
                ensure_karaoke_stems(out_dir, src, skeleton)
            except Exception as sep_exc:
                update_song(song_id, error=f"分离降级：{sep_exc}")
                _fallback_media(src, out_dir)
            processing_debug.event(song_id, "separate", mode="mugen")
        elif skeleton.get("needs_separate", True):
            try:
                separate_vocals(src, out_dir)
            except Exception as sep_exc:
                update_song(song_id, error=f"分离降级：{sep_exc}")
                _fallback_media(src, out_dir)
            processing_debug.event(song_id, "separate", mode="onnx")
        elif not (out_dir / "karaoke.m4a").exists():
            _fallback_media(src, out_dir)
        from lovktv.pipeline.loudness import normalize_file

        normalize_file(src)
        processing_debug.event(song_id, "normalize", file="original.mp3")
        # Pre-timed lyrics are trustworthy only when they belong to the native
        # MV that will be played.  Downloaded/alternate audio (including
        # Kugou and Karaoke Mugen audio without a native video) still needs
        # vocal-based alignment.
        native_timed = _native_timed_matches_media(out_dir, skeleton, src)
        if (
            skeleton.get("needs_align", True)
            or not (out_dir / "lyrics.json").exists()
            or not native_timed
        ):
            _align_and_mtv(
                song_id,
                out_dir,
                src,
                lang or language,
                rebuild_mtv=not (skeleton.get("has_video") or _has_native_mtv(out_dir)),
            )
            processing_debug.finish(song_id, "ready" if (get_song(song_id) or {}).get("status") == "ready" else "running")
            return
        _finish_ready_lyrics(
            song_id,
            out_dir,
            src,
            lang or language,
            rebuild_mtv=not (skeleton.get("has_video") or _has_native_mtv(out_dir)),
        )
        processing_debug.finish(song_id, "ready")
    except Exception as exc:  # noqa: BLE001 — job must record any failure
        update_song(song_id, status="failed", error=str(exc))
        processing_debug.event(song_id, "failed", status="error", error=str(exc))
        processing_debug.finish(song_id, "failed", str(exc))


def _cue_source(cue: dict) -> str:
    return str(cue.get("source_text") or cue.get("text") or "")


def _has_native_mtv(out_dir: Path) -> bool:
    """True when the folder already has an official / Bilibili MV we must not overwrite."""
    import json

    if (out_dir / "mugen.mp4").exists() or (out_dir / "mugen.webm").exists():
        return True
    for name, key in (("skeleton.json", "has_video"), ("lyrics.json", "native_video")):
        path = out_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get(key):
            return True
    return False


def _native_timed_matches_media(out_dir: Path, skeleton: dict, src: Path) -> bool:
    """Decide whether pre-timed lyrics belong to the media being played.

    A native MV and its subtitle track normally have nearly identical end
    times.  If either duration cannot be probed, keep the historical Mugen
    fallback; otherwise require a small (8%, capped at 20s) difference.
    """
    has_video = bool(skeleton.get("has_video")) or (out_dir / "mtv.mp4").exists() or (
        out_dir / "mugen.mp4"
    ).exists()
    if not has_video:
        return False
    lyrics_path = out_dir / "lyrics.json"
    try:
        import json

        timeline = json.loads(lyrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    cues = timeline.get("cues") if isinstance(timeline, dict) else []
    subtitle_ms = max(
        [
            int(cue.get("end_ms") or cue.get("start_ms") or 0)
            for cue in cues
            if isinstance(cue, dict)
        ]
        or [0]
    )
    media = out_dir / "mtv.mp4"
    if not media.exists():
        media = out_dir / "mugen.mp4"
    if not media.exists():
        media = src
    media_ms = probe_duration_ms(media)
    if not subtitle_ms or not media_ms:
        source = skeleton.get("source")
        return isinstance(source, dict) and source.get("provider") == "karaoke-mugen"
    tolerance = min(20_000, max(5_000, int(media_ms * 0.08)))
    return abs(int(media_ms) - subtitle_ms) <= tolerance


def _stamp_native_video(timeline: dict, out_dir: Path) -> bool:
    if timeline.get("native_video") or _has_native_mtv(out_dir):
        timeline["native_video"] = True
        return True
    return False


def _preserve_timeline_annotations(previous: dict, timeline: dict) -> None:
    """Carry trusted display annotations across an ASR-only realignment.

    Alignment regenerates cues and tokens, but their source text is usually
    unchanged.  Keep the previous Chinese line/word translations (and other
    display metadata) so a transient translation-agent failure cannot turn a
    previously translated song into a blank one.
    """
    if not isinstance(previous, dict) or not isinstance(timeline, dict):
        return
    for key in ("native_video", "translation", "translation_model", "annotation", "annotation_model"):
        if previous.get(key) and not timeline.get(key):
            timeline[key] = previous[key]

    old_by_source: dict[str, list[dict]] = {}
    for cue in previous.get("cues") or []:
        if not isinstance(cue, dict):
            continue
        source = lyric_source_key(cue.get("source_text") or cue.get("text") or "")
        if source:
            old_by_source.setdefault(source, []).append(cue)

    used: dict[str, int] = {}
    for cue in timeline.get("cues") or []:
        if not isinstance(cue, dict):
            continue
        source = lyric_source_key(cue.get("source_text") or cue.get("text") or "")
        rows = old_by_source.get(source) or []
        index = used.get(source, 0)
        if index >= len(rows):
            continue
        old = rows[index]
        used[source] = index + 1
        if old.get("zh") and not cue.get("zh"):
            cue["zh"] = old["zh"]

        old_tokens = [token for token in old.get("tokens") or [] if isinstance(token, dict)]
        new_tokens = [token for token in cue.get("tokens") or [] if isinstance(token, dict)]
        if not old_tokens or not new_tokens:
            continue
        # Match repeated words in order; this handles punctuation and small
        # tokenization changes without assigning a gloss to the wrong word.
        cursor = 0
        for token in new_tokens:
            wanted = lyric_source_key(token.get("text") or "")
            match = None
            for old_index in range(cursor, len(old_tokens)):
                if lyric_source_key(old_tokens[old_index].get("text") or "") == wanted:
                    match = old_tokens[old_index]
                    cursor = old_index + 1
                    break
            if match and match.get("zh") and not token.get("zh"):
                token["zh"] = match["zh"]


def _annotate_ja_timeline(song_id: str, out_dir: Path, timeline: dict) -> bool:
    cues = timeline.get("cues") or []
    if not cues:
        return False
    song = get_song(song_id) or {}
    lines = [_cue_source(cue) for cue in cues]
    force = any(line_is_romaji(line) for line in lines)
    try:
        notes = annotate_ja_lines(
            lines,
            title=str(song.get("title") or ""),
            artist=str(song.get("artist") or ""),
            cache_path=out_dir / "ja-annotate.json",
            force=force,
        )
        apply_ja_annotation(timeline, notes)
        from lovktv.workers.restore_ja import pack_timeline_to_voice

        pack_timeline_to_voice(timeline, out_dir)
        previous = str((get_song(song_id) or {}).get("error") or "")
        if "注音降级" in previous:
            update_song(song_id, error="")
        return True
    except Exception as ann_exc:
        previous = str((get_song(song_id) or {}).get("error") or "").strip()
        update_song(song_id, error=f"{previous} 注音降级：{ann_exc}".strip())
        return False


def _translate_foreign_timeline(
    song_id: str,
    out_dir: Path,
    timeline: dict,
    language: str | None,
    *,
    force: bool = False,
) -> bool:
    cues = timeline.get("cues") or []
    if not cues:
        return False
    language_key = str(language or timeline.get("language") or "").strip().lower()
    if is_chinese_lang(language_key):
        # Chinese/Cantonese lines normally need no translation.  Mixed lines
        # still need the same word-level glosses as English runs in Japanese
        # lyrics (for example ``我嘅 My jealous 心情``), so let the translator
        # handle only those cues and keep pure-CJK lines agent-free.
        if not any(re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", _cue_source(cue)) for cue in cues):
            return False
    cache_path = out_dir / "zh-translate.json"
    cache_stale = False
    if cache_path.exists():
        try:
            import json

            cache_stale = json.loads(cache_path.read_text(encoding="utf-8")).get(
                "schema"
            ) != TRANSLATE_SCHEMA
        except (OSError, ValueError, TypeError):
            cache_stale = True
    force = force or cache_stale
    if not force and all(str(cue.get("zh") or "").strip() for cue in cues):
        # A cached line translation can coexist with an untranslated English
        # token (most commonly a contraction such as ``'Cause``/``it's``).
        # Re-enter the lightweight translation pass so token-level fallbacks
        # are applied; credit lines are metadata, not lyric words.
        missing_word = any(
            not re.search(r"[:：]", str(cue.get("text") or _cue_source(cue)))
            and any(
                re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", str(token.get("text") or ""))
                and not str(token.get("zh") or token.get("translation") or "").strip()
                for token in (cue.get("tokens") or [])
            )
            for cue in cues
        )
        if not missing_word:
            return False
    song = get_song(song_id) or {}
    lines = [str(cue.get("text") or _cue_source(cue)) for cue in cues]
    try:
        notes = translate_lines(
            lines,
            title=str(song.get("title") or ""),
            artist=str(song.get("artist") or ""),
            language=str(language or timeline.get("language") or ""),
            cache_path=cache_path,
            force=force,
        )
        apply_zh_translation(timeline, notes, overwrite=force)
        previous = str((get_song(song_id) or {}).get("error") or "")
        if "翻译降级" in previous:
            update_song(song_id, error="")
        return True
    except Exception as tr_exc:
        previous = str((get_song(song_id) or {}).get("error") or "").strip()
        update_song(song_id, error=f"{previous} 翻译降级：{tr_exc}".strip())
        return False


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
    processing_debug.event(song_id, "lyrics", count=len(timeline.get("cues") or []), source="persisted")
    song = get_song(song_id) or {}
    blob = "".join(_cue_source(cue) for cue in timeline.get("cues") or [])
    lang = resolve_language(
        blob, language, timeline.get("language"), song.get("language")
    )
    timeline["language"] = lang
    burned = bool(timeline.get("burned_lyrics"))
    official = _stamp_native_video(timeline, out_dir)
    if lang == "ja" and not burned:
        update_song(song_id, language=lang, status="annotating")
    else:
        update_song(song_id, language=lang, status="ready")
        _publish_ready(song_id)
    wrote = False
    if lang == "ja" and timeline.get("cues") and not burned:
        processing_debug.event(song_id, "annotation", status="running", language=lang)
        wrote = _annotate_ja_timeline(song_id, out_dir, timeline)
    if timeline.get("cues") and not burned:
        wrote = _translate_foreign_timeline(song_id, out_dir, timeline, lang) or wrote
        processing_debug.event(song_id, "translation", language=lang)
    if wrote or (timeline.get("native_video") and not burned):
        write_subtitles(timeline, out_dir)
    update_song(song_id, status="ready")
    _publish_ready(song_id)
    if official or (not rebuild_mtv and (out_dir / "mtv.mp4").exists()):
        return
    song = get_song(song_id) or {}
    audio = out_dir / "karaoke.m4a"
    if not audio.exists():
        audio = src
    cover = out_dir / "cover.jpg"
    try:
        processing_debug.event(song_id, "compose-mtv", status="running")
        compose_mtv(
            out_dir,
            audio_path=audio,
            title=str(song.get("title") or "lov-ktv"),
            artist=str(song.get("artist") or ""),
            timeline=timeline,
            cover_path=cover if cover.exists() else None,
        )
        processing_debug.event(song_id, "compose-mtv", files=["mtv.mp4"])
        _publish_ready(song_id)
    except Exception as mtv_exc:
        processing_debug.event(song_id, "compose-mtv", status="error", error=str(mtv_exc))
        previous = str(song.get("error") or "").strip()
        update_song(song_id, error=f"{previous} MTV降级：{mtv_exc}".strip())


def process_upload(song_id: str, src: Path, language: str | None = None) -> None:
    out_dir = MEDIA_DIR / song_id
    processing_debug.start(song_id, "upload")
    try:
        update_song(song_id, status="separating")
        processing_debug.event(song_id, "separate", status="running", source=str(src.name))
        if not src.exists():
            raise RuntimeError("没有上传音频")
        try:
            separate_vocals(src, out_dir)
        except Exception as sep_exc:
            update_song(song_id, error=f"分离降级：{sep_exc}")
            _fallback_media(src, out_dir)
        _align_and_mtv(song_id, out_dir, src, language, rebuild_mtv=True)
        processing_debug.finish(song_id, "ready")
    except Exception as exc:  # noqa: BLE001
        update_song(song_id, status="failed", error=str(exc))
        processing_debug.event(song_id, "failed", status="error", error=str(exc))
        processing_debug.finish(song_id, "failed", str(exc))


def load_lyric_lines(out_dir: Path, language: str | None = None) -> list[dict]:
    path = out_dir / "lyrics.lrc"
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    lines = parse_lrc(raw) or parse_plain_lines(raw)
    lang = resolve_language("".join(item.get("text") or "" for item in lines), language)
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
    lang = resolve_language(
        "".join(str(item.get("text") or "") for item in rows),
        existing.get("language"),
        (get_song(song_id) or {}).get("language"),
    )
    rows = prepare_lyric_lines(rows, lang)
    src = out_dir / "original.mp3"
    timeline = rebuild_manual_timeline(
        rows, existing, probe_duration_ms(src) if src.exists() else None
    )
    notes_path = out_dir / "ja-annotate.json"
    if lang == "ja":
        if notes_path.exists() and not any(
            line_is_romaji(_cue_source(cue)) for cue in timeline.get("cues") or []
        ):
            apply_ja_annotation(
                timeline, json.loads(notes_path.read_text(encoding="utf-8"))
            )
        else:
            _annotate_ja_timeline(song_id, out_dir, timeline)
    voice = out_dir / "vocals.wav"
    if not voice.exists():
        voice = src
    if voice.exists():
        envelope, hop_ms = extract_envelope(voice)
        pack_tokens_to_singing(timeline["cues"], envelope, hop_ms)
    _translate_foreign_timeline(song_id, out_dir, timeline, lang)
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


def process_realign(
    song_id: str,
    language: str | None = None,
    rebuild_mtv: bool = False,
    force: bool = False,
) -> None:
    """Re-run the same ASR + lyric pipeline used by import/upload."""
    out_dir = MEDIA_DIR / song_id
    processing_debug.start(song_id, "realign")
    processing_debug.event(song_id, "realign", status="running", force=force)
    src = out_dir / "original.mp3"
    if not src.exists():
        src = _voice_audio(out_dir, out_dir / "karaoke.m4a")
    try:
        if not src.exists():
            if force:
                # A forced media refresh must also recover songs whose local
                # volume was removed after it had been published to OSS.  In
                # that case there is no clock to realign; re-import the
                # pinned source first so the normal import pipeline rebuilds
                # original/vocals/karaoke and lyrics together.
                song = get_song(song_id) or {}
                query = retry_query(song)
                if not query:
                    raise RuntimeError("没有可重新导入的歌曲信息")
                process_import(
                    song_id,
                    query,
                    str(song.get("netease_id") or ""),
                    language or song.get("language"),
                )
                return
            raise RuntimeError("没有可对齐的音频")
        # Karaoke Mugen subtitles are authored against their own media clock;
        # running Whisper/agent alignment over them only destroys trusted
        # word timings. Keep the pre-timed timeline on manual realign too.
        skeleton_path = out_dir / "skeleton.json"
        skeleton = {}
        if skeleton_path.exists():
            skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
        # A Mugen off-vocal MV is intentionally the karaoke stem.  On a
        # forced refresh restore its recorded vocal sibling before the trusted
        # Mugen timeline fast path returns; otherwise the old MV extraction
        # would leave both published tracks as accompaniment.
        mugen_off_vocal = _is_mugen_off_vocal(skeleton)
        if force and mugen_off_vocal:
            src = _refresh_audio_tracks(out_dir, skeleton)
        if (out_dir / "lyrics.manual.lrc").exists():
            apply_locked_manual(song_id, rebuild_mtv=rebuild_mtv)
            processing_debug.finish(song_id, "ready")
            return
        if _is_mugen_skeleton(skeleton) and (out_dir / "lyrics.json").exists():
            _restore_mugen_timeline(out_dir, language or skeleton.get("language"))
            _finish_ready_lyrics(song_id, out_dir, src, language, rebuild_mtv)
            processing_debug.finish(song_id, "ready")
            return
        if force and not mugen_off_vocal:
            src = _refresh_audio_tracks(out_dir, skeleton)
        if force:
            # A user-requested recalculation must not silently reuse stale
            # Whisper or agent alignment caches from the previous run.
            for path in (out_dir / "asr.json", out_dir / "agent-align.json"):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            cache_dir = out_dir / "_asr"
            if cache_dir.is_dir():
                for path in cache_dir.glob("*.json"):
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
        _align_and_mtv(song_id, out_dir, src, language, rebuild_mtv=rebuild_mtv)
        processing_debug.finish(song_id, "ready")
    except Exception as exc:  # noqa: BLE001
        update_song(song_id, status="failed", error=str(exc))
        processing_debug.event(song_id, "failed", status="error", error=str(exc))
        processing_debug.finish(song_id, "failed", str(exc))


def _restore_mugen_timeline(out_dir: Path, language: str | None = None) -> bool:
    """Rebuild a trusted Mugen timeline from its untouched ASS source."""
    ass_path = out_dir / "mugen.ass"
    if not ass_path.exists():
        return False
    previous: dict = {}
    lyrics_path = out_dir / "lyrics.json"
    if lyrics_path.exists():
        try:
            previous = json.loads(lyrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            previous = {}
    try:
        from lovktv.catalog.mugen import timeline_from_ass

        timeline = timeline_from_ass(
            ass_path.read_text(encoding="utf-8", errors="replace"), language or "ja"
        )
        _preserve_timeline_annotations(previous, timeline)
        timeline["native_video"] = _has_native_mtv(out_dir) or bool(
            previous.get("native_video")
        )
        write_subtitles(timeline, out_dir)
        return True
    except (OSError, UnicodeError, RuntimeError):
        return False


def _fetch_alternate_kugou_timeline(
    song_id: str, song: dict[str, Any], out_dir: Path
) -> dict[str, Any] | None:
    """Fetch an authored lyric version using the source video's singer/title."""
    bvid = str(song.get("netease_id") or "").strip()
    if not is_bvid(bvid):
        return None
    try:
        payload = api_get(f"{VIEW_URL}?bvid={bvid}", timeout=10)
        title = str((payload.get("data") or {}).get("title") or "")
    except Exception:
        # Some datacenter egresses return Bilibili 412 to urllib's request
        # fingerprint while accepting curl's browser-like request.
        try:
            result = subprocess.run(
                ["curl", "-fsS", "--max-time", "10", "-A", "Mozilla/5.0",
                 f"{VIEW_URL}?bvid={bvid}"],
                capture_output=True, text=True, check=False, timeout=15,
            )
            payload = json.loads(result.stdout or "{}")
            title = str((payload.get("data") or {}).get("title") or "")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None
    match = re.search(r"([^《】]{2,24})《([^》]{2,80})》", title)
    if not match:
        return None
    artist_parts = re.findall(r"[\u4e00-\u9fffA-Za-z·]{2,12}", match.group(1))
    artist = artist_parts[-1].strip() if artist_parts else ""
    lyric_title = re.sub(r"[（(][^）)]{0,20}[）)]", "", match.group(2)).strip()
    if not artist or not lyric_title:
        return None
    result = fetch_kugou_lyrics(lyric_title, artist)
    timeline = result.get("timeline") if result else None
    if not isinstance(timeline, dict) or not timeline.get("cues"):
        return None
    try:
        write_subtitles(timeline, out_dir)
        write_manual_lrc(out_dir, timeline["cues"])
    except OSError:
        return None
    return timeline


def _align_and_mtv(
    song_id: str,
    out_dir: Path,
    src: Path,
    language: str | None,
    rebuild_mtv: bool = True,
) -> None:
    song = get_song(song_id) or {}
    processing_debug.event(song_id, "align", status="running")
    previous_timeline: dict = {}
    lyrics_path = out_dir / "lyrics.json"
    if lyrics_path.exists():
        try:
            previous_timeline = json.loads(lyrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            previous_timeline = {}
    # Snapshot this before writing the regenerated timeline.  The list MV
    # badge is derived from persisted media metadata, so it must survive even
    # if a later subtitle/translation step is degraded.
    had_native_video = _has_native_mtv(out_dir) or bool(
        previous_timeline.get("native_video")
    )
    lines = load_lyric_lines(out_dir, language)
    processing_debug.event(song_id, "lyrics", count=len(lines), language=language or "")
    lang = resolve_language("".join(item.get("text") or "" for item in lines), language)
    update_song(song_id, language=lang, status="aligning")
    voice = _ensure_vocals(out_dir, src)
    prompt = "\n".join(str(item.get("text") or "") for item in lines[:10])
    asr_words = transcribe_words(
        voice,
        lang,
        cache_path=out_dir / "asr.json",
        prompt=prompt,
    )
    processing_debug.event(song_id, "asr", count=len(asr_words or []), cache="asr.json")
    agent_matches = align_lines_with_agent(
        lines,
        asr_words,
        lang,
        cache_path=out_dir / "agent-align.json",
    )
    processing_debug.event(song_id, "agent-align", count=len(agent_matches or []), cache="agent-align.json")
    align_kwargs = {
        "audio_path": voice,
        "duration_ms": probe_duration_ms(src) or probe_duration_ms(voice),
        "asr_words": asr_words or None,
    }
    if agent_matches:
        align_kwargs["agent_matches"] = agent_matches
    # If the selected LRC is a different (often Mandarin) version, prefer
    # the official Cantonese KRC when the Bilibili title exposes the singer.
    # ASR is useful for detecting the mismatch, but its transcript is not a
    # substitute for authored lyrics.
    alternate = None
    if _looks_like_wrong_lyric_version(lines, asr_words, agent_matches, lang):
        alternate = _fetch_alternate_kugou_timeline(song_id, song, out_dir)
    if alternate:
        timeline = alternate
        lang = str(timeline.get("language") or lang)
    else:
        timeline = align_lyrics(lines, lang, **align_kwargs)
    processing_debug.event(song_id, "timeline", cues=len(timeline.get("cues") or []), source=timeline.get("alignment_source") or "")
    _preserve_timeline_annotations(previous_timeline, timeline)
    if had_native_video:
        timeline["native_video"] = True
    keep_native = _stamp_native_video(timeline, out_dir) or had_native_video
    if lang == "ja" and timeline.get("cues"):
        update_song(song_id, status="annotating")
        _annotate_ja_timeline(song_id, out_dir, timeline)
        if keep_native:
            timeline["native_video"] = True
    if timeline.get("cues"):
        update_song(song_id, status="annotating")
        _translate_foreign_timeline(song_id, out_dir, timeline, lang)
        processing_debug.event(song_id, "translation", language=lang)
        if keep_native:
            timeline["native_video"] = True
    if timeline.get("cues"):
        write_subtitles(timeline, out_dir)
    update_song(song_id, status="ready")
    processing_debug.event(song_id, "ready", files=sorted(path.name for path in out_dir.iterdir()) if out_dir.exists() else [])
    _publish_ready(song_id)
    if keep_native or (not rebuild_mtv and (out_dir / "mtv.mp4").exists()):
        return
    song = get_song(song_id) or {}
    audio = out_dir / "karaoke.m4a"
    if not audio.exists():
        audio = src
    cover = out_dir / "cover.jpg"
    try:
        processing_debug.event(song_id, "compose-mtv", status="running")
        compose_mtv(
            out_dir,
            audio_path=audio,
            title=str(song.get("title") or "lov-ktv"),
            artist=str(song.get("artist") or ""),
            timeline=timeline,
            cover_path=cover if cover.exists() else None,
        )
        processing_debug.event(song_id, "compose-mtv", files=["mtv.mp4"])
        _publish_ready(song_id)
    except Exception as mtv_exc:
        processing_debug.event(song_id, "compose-mtv", status="error", error=str(mtv_exc))
        previous = str(song.get("error") or "").strip()
        note = f"MTV降级：{mtv_exc}"
        update_song(song_id, error=f"{previous} {note}".strip())


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


class _ModuleSongRepository:
    """Compatibility adapter that keeps monkeypatchable module seams alive."""

    def list(self) -> list[dict]:
        return list_songs()

    def retry_query(self, song: dict) -> str:
        return retry_query(song)


class JobRecovery:
    """Find persisted songs that need to be queued again after a restart."""

    def __init__(
        self,
        repository: SongRepository | None = None,
        submit: Callable[..., Any] | None = None,
        media_dir: Path | None = None,
    ) -> None:
        self.repository = repository or _ModuleSongRepository()
        self.submit = submit
        self.media_dir = media_dir or MEDIA_DIR

    def resume(self) -> int:
        """Continue songs left queued/aligning after a reload killed the worker."""
        submit = self.submit or spawn
        media_dir = self.media_dir
        songs = self.repository
        resumed = 0
        pending_finish: list[tuple] = []
        pending_align: list[tuple] = []
        pending_import: list[tuple] = []
        for song in reversed(songs.list()):
            status = str(song.get("status") or "")
            song_id = str(song["id"])
            out_dir = media_dir / song_id
            has_audio = (out_dir / "original.mp3").exists() or (
                out_dir / "vocals.wav"
            ).exists()
            if (
                status in {"aligning", "annotating", "composing", "separating"}
                and has_audio
            ):
                if _has_ready_lyrics(out_dir):
                    pending_finish.append((song_id, out_dir, song.get("language")))
                else:
                    pending_align.append((song_id, song.get("language")))
                continue
            if status in {"queued", "fetching"}:
                pending_import.append(
                    (
                        song_id,
                        songs.retry_query(song),
                        str(song.get("netease_id") or ""),
                        song.get("language"),
                    )
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
            submit(_finish_ready_lyrics, song_id, out_dir, src, language, False)
            resumed += 1
        for song_id, language in pending_align:
            submit(
                process_realign,
                song_id,
                language,
                not _has_native_mtv(media_dir / song_id),
            )
            resumed += 1
        for song_id, query, netease_id, language in pending_import:
            submit(process_import, song_id, query, netease_id, language)
            resumed += 1
        if resumed:
            print(f"[lovktv] resume {resumed} stuck songs", flush=True)
        return resumed


def resume_stuck_jobs() -> int:
    """Compatibility wrapper for the injectable :class:`JobRecovery`."""
    return JobRecovery().resume()
