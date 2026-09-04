"""Audit published lyrics and repair the two recurring agent mistakes.

1. A "Chinese" translation that is not Chinese (English, romaji, or the
   source copied back), on a line or on a word gloss.
2. A Japanese line still shown as romaji because the annotation agent put the
   romaji in ``surface`` and the kana in ``reading``.

``python -m lovktv.workers.lyric_audit`` reports; ``--fix`` rewrites the
timelines (reusing cached notes wherever possible) and republishes them.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from lovktv.agents.ja_lyrics import (
    annotate_ja_lines,
    apply_ja_annotation,
    line_is_romaji,
    valid_zh,
)
from lovktv.agents.translate import is_chinese_lang
from lovktv.core.config import MEDIA_DIR
from lovktv.pipeline.lyrics import is_credit_lyric, write_subtitles
from lovktv.storage.store import get_song, list_songs, update_song

_LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_JA_SCRIPT = re.compile(r"[぀-ヿ㐀-鿿豈-﫿]")


def _cue_source(cue: dict[str, Any]) -> str:
    return str(cue.get("source_text") or cue.get("text") or "")


def _cue_text(cue: dict[str, Any]) -> str:
    return str(cue.get("text") or cue.get("source_text") or "")


def token_is_unrestored_romaji(token: dict[str, Any]) -> bool:
    """A sung piece still displayed as romaji: Latin text carrying a romaji
    pronunciation of itself.  Real English words (``Stay``, ``love``) have no
    romaji, so they are not flagged."""
    text = str(token.get("text") or token.get("surface") or "").strip()
    if not text or _JA_SCRIPT.search(text) or not _LATIN.search(text):
        return False
    pronunciation = token.get("pronunciation")
    pron_value = (
        str(pronunciation.get("value") or "").strip()
        if isinstance(pronunciation, dict)
        else ""
    )
    romaji = str(token.get("romaji") or pron_value).strip()
    if not romaji:
        return False
    return re.sub(r"[^a-z]", "", romaji.lower()) == re.sub(r"[^a-z]", "", text.lower())


def cue_is_unrestored_romaji(cue: dict[str, Any]) -> bool:
    if not line_is_romaji(_cue_text(cue)):
        return False
    # Some persisted timelines have already been tokenized into Japanese, but
    # the cue-level ``text``/``surface`` was left as the original romaji.  The
    # player renders the cue surface, so this is still an unrestored line even
    # though individual tokens no longer carry a romaji-looking ``text``.
    if any(
        _JA_SCRIPT.search(str(token.get("text") or token.get("surface") or ""))
        for token in cue.get("tokens") or []
        if isinstance(token, dict)
    ):
        return True
    return any(token_is_unrestored_romaji(token) for token in cue.get("tokens") or [])


_SOLFEGE = {"do", "re", "mi", "fa", "so", "sol", "la", "si", "ti", "oh", "ah", "la-la"}


def _is_solfege(text: str) -> bool:
    words = [word.lower() for word in re.findall(r"[A-Za-z\-]+", text)]
    return bool(words) and all(word in _SOLFEGE for word in words)


def _needs_translation(language: str, cue: dict[str, Any]) -> bool:
    text = _cue_text(cue)
    if is_credit_lyric(text) or _is_solfege(text):
        return False
    if not _LATIN.search(text) and not _JA_SCRIPT.search(text):
        return False
    if is_chinese_lang(language):
        # A Chinese song only needs a line translation for a fully foreign
        # line; mixed lines get their English words glossed token by token.
        return bool(_LATIN.search(text)) and not valid_zh(text)
    return True


def audit_timeline(timeline: dict[str, Any]) -> dict[str, Any]:
    language = str(timeline.get("language") or "").strip().lower()
    cues = [cue for cue in timeline.get("cues") or [] if isinstance(cue, dict)]
    romaji_cues: list[str] = []
    bad_line_zh: list[dict[str, str]] = []
    bad_token_zh: list[dict[str, str]] = []
    missing_line_zh: list[str] = []
    for cue in cues:
        text = _cue_text(cue)
        if language == "ja" and cue_is_unrestored_romaji(cue):
            romaji_cues.append(text)
        raw_zh = str(cue.get("zh") or cue.get("translation") or "").strip()
        if raw_zh and not valid_zh(raw_zh) and _needs_translation(language, cue):
            bad_line_zh.append({"text": text, "zh": raw_zh})
        elif not raw_zh and _needs_translation(language, cue):
            missing_line_zh.append(text)
        for token in cue.get("tokens") or []:
            if not isinstance(token, dict):
                continue
            gloss = str(token.get("zh") or token.get("translation") or "").strip()
            if gloss and not valid_zh(gloss):
                bad_token_zh.append(
                    {"text": text, "token": str(token.get("text") or ""), "zh": gloss}
                )
    return {
        "language": language,
        "cues": len(cues),
        "romaji_cues": romaji_cues,
        "bad_line_zh": bad_line_zh,
        "bad_token_zh": bad_token_zh,
        "missing_line_zh": missing_line_zh,
        "ok": not (romaji_cues or bad_line_zh or bad_token_zh or missing_line_zh),
    }


def _load_timeline(song_id: str) -> tuple[Path, dict[str, Any] | None]:
    out_dir = MEDIA_DIR / song_id
    path = out_dir / "lyrics.json"
    if not path.exists():
        return out_dir, None
    try:
        timeline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out_dir, None
    return out_dir, timeline if isinstance(timeline, dict) else None


def audit_song(song_id: str) -> dict[str, Any]:
    _out_dir, timeline = _load_timeline(song_id)
    song = get_song(song_id) or {}
    base = {
        "id": song_id,
        "title": str(song.get("title") or ""),
        "artist": str(song.get("artist") or ""),
    }
    if timeline is None:
        return {**base, "ok": True, "skipped": "no-lyrics"}
    if timeline.get("burned_lyrics"):
        return {**base, "ok": True, "skipped": "burned"}
    return {**base, **audit_timeline(timeline)}


def _clear_invalid_zh(timeline: dict[str, Any]) -> int:
    cleared = 0
    for cue in timeline.get("cues") or []:
        if not isinstance(cue, dict):
            continue
        raw = str(cue.get("zh") or cue.get("translation") or "").strip()
        if raw and not valid_zh(raw):
            cue.pop("zh", None)
            cue.pop("translation", None)
            cleared += 1
        for token in cue.get("tokens") or []:
            if not isinstance(token, dict):
                continue
            gloss = str(token.get("zh") or token.get("translation") or "").strip()
            if gloss and not valid_zh(gloss):
                token.pop("zh", None)
                token["translation"] = ""
                cleared += 1
    return cleared


def _notes_cover(notes: dict[str, Any], lines: list[str]) -> bool:
    from lovktv.agents.ja_lyrics import lyric_source_key

    known = {
        lyric_source_key(item.get("source") or "")
        for item in notes.get("lines") or []
        if isinstance(item, dict) and item.get("units")
    }
    return all(lyric_source_key(line) in known for line in lines)


def _restore_romaji(song_id: str, out_dir: Path, timeline: dict[str, Any]) -> str:
    """Bring romaji cues back to Japanese: cached notes first, agent second.

    The agent is only asked again when the cached notes do not cover the
    romaji lines; if it already answered and the line still cannot be
    restored (a vocalization such as ``tuturu``), the audit keeps reporting
    it instead of paying for the same answer on every run.
    """
    from lovktv.workers.restore_ja import pack_timeline_to_voice

    song = get_song(song_id) or {}
    notes_path = out_dir / "ja-annotate.json"
    if notes_path.exists():
        try:
            notes = json.loads(notes_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            notes = {}
        if notes.get("lines"):
            apply_ja_annotation(timeline, notes)
            pack_timeline_to_voice(timeline, out_dir)
            leftover = audit_timeline(timeline)["romaji_cues"]
            if not leftover:
                return "reapplied"
            if _notes_cover(notes, leftover):
                return "reapplied-partial"
    lines = [_cue_source(cue) for cue in timeline.get("cues") or []]
    notes = annotate_ja_lines(
        lines,
        title=str(song.get("title") or ""),
        artist=str(song.get("artist") or ""),
        cache_path=notes_path,
        force=True,
    )
    apply_ja_annotation(timeline, notes)
    pack_timeline_to_voice(timeline, out_dir)
    return "annotated"


def repair_song(song_id: str, publish: bool = True) -> dict[str, Any]:
    from lovktv.workers.jobs import _translate_foreign_timeline

    out_dir, timeline = _load_timeline(song_id)
    before = audit_song(song_id)
    if timeline is None or before.get("skipped") or before["ok"]:
        return {**before, "changed": False}
    actions: list[str] = []
    language = str(timeline.get("language") or "").strip().lower()
    if language == "ja" and before["romaji_cues"]:
        actions.append(_restore_romaji(song_id, out_dir, timeline))
    if _clear_invalid_zh(timeline):
        actions.append("cleared-zh")
    after = audit_timeline(timeline)
    translated: bool | None = None
    if after["missing_line_zh"] or after["bad_token_zh"] or any(
        not valid_zh(token.get("zh") or "")
        and _LATIN.search(str(token.get("text") or ""))
        for cue in timeline.get("cues") or []
        for token in cue.get("tokens") or []
    ):
        # Fills empty / cleared translations through the normal pipeline
        # step (cache first, agent second) and records ``翻译降级`` on the
        # song when the agent is unavailable.
        translated = _translate_foreign_timeline(song_id, out_dir, timeline, language)
        if translated:
            actions.append("translated")
    write_subtitles(timeline, out_dir)
    published: list[str] = []
    if publish:
        from lovktv.media.oss import publish_song

        published = publish_song(song_id)
    final = audit_song(song_id)
    error = str((get_song(song_id) or {}).get("error") or "")
    degraded = "注音降级" in error or "翻译降级" in error
    if degraded and translated is not False and not final["romaji_cues"]:
        update_song(song_id, error="")
        error = ""
    result = {**final, "changed": True, "actions": actions, "published": published}
    if error:
        result["error"] = error
        result["ok"] = False
    return result


def run(
    song_ids: list[str] | None = None, fix: bool = False, publish: bool = True
) -> list[dict[str, Any]]:
    ids = song_ids or [row["id"] for row in list_songs()]
    results: list[dict[str, Any]] = []
    for song_id in ids:
        try:
            results.append(repair_song(song_id, publish=publish) if fix else audit_song(song_id))
        except Exception as exc:  # noqa: BLE001
            results.append({"id": song_id, "ok": False, "error": str(exc)})
    return results


def _summary(item: dict[str, Any]) -> str:
    if item.get("skipped"):
        return f"skip:{item['skipped']}"
    if item.get("error"):
        return f"error:{item['error']}"
    bits = []
    if item.get("romaji_cues"):
        bits.append(f"romaji={len(item['romaji_cues'])}")
    if item.get("bad_line_zh"):
        bits.append(f"en-line={len(item['bad_line_zh'])}")
    if item.get("bad_token_zh"):
        bits.append(f"en-word={len(item['bad_token_zh'])}")
    if item.get("missing_line_zh"):
        bits.append(f"no-zh={len(item['missing_line_zh'])}")
    status = "ok" if item.get("ok") else " ".join(bits) or "bad"
    if item.get("changed"):
        status += " <- " + ",".join(item.get("actions") or ["-"])
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit / repair lyric translations and Japanese restore")
    parser.add_argument("song_ids", nargs="*", help="Song ids; default is the whole catalog")
    parser.add_argument("--fix", action="store_true", help="Rewrite and republish problem songs")
    parser.add_argument("--no-publish", action="store_true", help="Do not upload to OSS after fixing")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    parser.add_argument("--all", action="store_true", help="Also list songs that are fine")
    args = parser.parse_args()
    results = run(args.song_ids or None, fix=args.fix, publish=not args.no_publish)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            if item.get("ok") and not item.get("changed") and not args.all:
                continue
            label = f"{item.get('title') or ''} · {item.get('artist') or ''}".strip(" ·")
            print(f"{item['id']} {item.get('language') or '-':>2} {_summary(item):<40} {label}", flush=True)
    bad = [item for item in results if not item.get("ok")]
    print(
        f"songs {len(results)} problem {len(bad)}"
        + (f" fixed {sum(1 for item in results if item.get('changed') and item.get('ok'))}" if args.fix else ""),
        flush=True,
    )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
