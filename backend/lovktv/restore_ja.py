"""Re-annotate Japanese lyrics so Mugen romaji becomes Japanese."""

from __future__ import annotations

import argparse
import json

from lovktv.agents.ja_lyrics import annotate_ja_lines, apply_ja_annotation, line_is_romaji
from lovktv.config import MEDIA_DIR
from lovktv.pipeline.lyrics import write_subtitles
from lovktv.store import get_song, list_songs, update_song

LYRIC_PUBLISH_NAMES = (
    "lyrics.json",
    "lyrics.elrc",
    "lyrics.ass",
    "ja-annotate.json",
)


def _publish_lyrics(song_id: str) -> list[str]:
    from lovktv.oss import oss_ready, put_file

    if not oss_ready():
        return []
    uploaded: list[str] = []
    folder = MEDIA_DIR / song_id
    for name in LYRIC_PUBLISH_NAMES:
        path = folder / name
        if path.exists():
            put_file(song_id, path)
            uploaded.append(name)
    return uploaded


def pack_timeline_to_voice(timeline: dict, out_dir) -> bool:
    """Sweep karaoke tokens over the sung burst, not the hold until the next line."""
    from lovktv.pipeline.align import extract_envelope, pack_tokens_to_singing

    for name in ("vocals.wav", "karaoke.m4a", "original.mp3"):
        audio = out_dir / name
        if not audio.exists():
            continue
        envelope, hop_ms = extract_envelope(audio)
        if not envelope:
            continue
        pack_tokens_to_singing(timeline.get("cues") or [], envelope, hop_ms)
        return True
    return False


def cue_source(cue: dict) -> str:
    return str(cue.get("source_text") or cue.get("text") or "")


def needs_romaji_restore(timeline: dict) -> bool:
    if str(timeline.get("language") or "") != "ja":
        return False
    return any(line_is_romaji(cue.get("text") or "") for cue in timeline.get("cues") or [])


def already_restored(timeline: dict) -> bool:
    return any(
        line_is_romaji(str(cue.get("source_text") or "")) and not line_is_romaji(str(cue.get("text") or ""))
        for cue in timeline.get("cues") or []
    )


def restore_song(
    song_id: str,
    force: bool = False,
    publish: bool = True,
    reapply: bool = False,
) -> dict:
    out_dir = MEDIA_DIR / song_id
    lyrics_path = out_dir / "lyrics.json"
    notes_path = out_dir / "ja-annotate.json"
    if not lyrics_path.exists():
        return {"id": song_id, "ok": False, "reason": "no-lyrics"}
    timeline = json.loads(lyrics_path.read_text(encoding="utf-8"))
    if str(timeline.get("language") or "") != "ja":
        return {"id": song_id, "ok": False, "reason": "not-ja"}
    song = get_song(song_id) or {}
    if reapply:
        if not notes_path.exists():
            return {"id": song_id, "ok": False, "reason": "no-notes"}
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
    else:
        if not force and already_restored(timeline):
            return {"id": song_id, "ok": False, "reason": "already-restored"}
        if not force and not needs_romaji_restore(timeline):
            return {"id": song_id, "ok": False, "reason": "no-romaji"}
        lines = [cue_source(cue) for cue in timeline.get("cues") or []]
        notes = annotate_ja_lines(
            lines,
            title=str(song.get("title") or ""),
            artist=str(song.get("artist") or ""),
            cache_path=notes_path,
            force=force or needs_romaji_restore(timeline),
        )
    apply_ja_annotation(timeline, notes)
    pack_timeline_to_voice(timeline, out_dir)
    write_subtitles(timeline, out_dir)
    previous = str(song.get("error") or "")
    if "注音降级" in previous:
        update_song(song_id, error="")
    if publish:
        names = _publish_lyrics(song_id) if reapply else None
        if names is None:
            from lovktv.oss import publish_song

            names = publish_song(song_id)
        return {"id": song_id, "ok": True, "published": names}
    return {"id": song_id, "ok": True, "published": []}


def restore_many(
    song_ids: list[str] | None = None,
    force: bool = False,
    publish: bool = True,
    reapply: bool = False,
) -> list[dict]:
    ids = song_ids or [row["id"] for row in list_songs()]
    results = []
    for song_id in ids:
        try:
            results.append(restore_song(song_id, force=force, publish=publish, reapply=reapply))
        except Exception as exc:  # noqa: BLE001
            results.append({"id": song_id, "ok": False, "reason": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore romaji Japanese lyrics via the JA agent")
    parser.add_argument("song_ids", nargs="*", help="Song ids; default is every ja song with romaji")
    parser.add_argument("--all", action="store_true", help="Scan the whole catalog")
    parser.add_argument("--force", action="store_true", help="Re-annotate even without romaji lines")
    parser.add_argument(
        "--reapply",
        action="store_true",
        help="Reuse ja-annotate.json and rewrite tokens without calling the agent",
    )
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()
    ids = None if args.all or not args.song_ids else args.song_ids
    results = restore_many(
        ids,
        force=args.force,
        publish=not args.no_publish,
        reapply=args.reapply,
    )
    restored = 0
    for item in results:
        status = "ok" if item.get("ok") else item.get("reason") or "fail"
        print(f"{item['id']} {status}", flush=True)
        restored += int(bool(item.get("ok")))
    print(f"restored {restored}/{len(results)}", flush=True)
    return 0 if restored or not results else 1


if __name__ == "__main__":
    raise SystemExit(main())
