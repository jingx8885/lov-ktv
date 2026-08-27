"""Re-annotate Japanese lyrics so Mugen romaji becomes Japanese."""

from __future__ import annotations

import argparse
import json

from lovktv.agents.ja_lyrics import annotate_ja_lines, apply_ja_annotation, line_is_romaji
from lovktv.config import MEDIA_DIR
from lovktv.pipeline.lyrics import write_subtitles
from lovktv.store import get_song, list_songs, update_song


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


def restore_song(song_id: str, force: bool = False, publish: bool = True) -> dict:
    out_dir = MEDIA_DIR / song_id
    lyrics_path = out_dir / "lyrics.json"
    if not lyrics_path.exists():
        return {"id": song_id, "ok": False, "reason": "no-lyrics"}
    timeline = json.loads(lyrics_path.read_text(encoding="utf-8"))
    if str(timeline.get("language") or "") != "ja":
        return {"id": song_id, "ok": False, "reason": "not-ja"}
    if not force and already_restored(timeline):
        return {"id": song_id, "ok": False, "reason": "already-restored"}
    if not force and not needs_romaji_restore(timeline):
        return {"id": song_id, "ok": False, "reason": "no-romaji"}
    song = get_song(song_id) or {}
    lines = [cue_source(cue) for cue in timeline.get("cues") or []]
    notes = annotate_ja_lines(
        lines,
        title=str(song.get("title") or ""),
        artist=str(song.get("artist") or ""),
        cache_path=out_dir / "ja-annotate.json",
        force=force or needs_romaji_restore(timeline),
    )
    apply_ja_annotation(timeline, notes)
    write_subtitles(timeline, out_dir)
    previous = str(song.get("error") or "")
    if "注音降级" in previous:
        update_song(song_id, error="")
    if publish:
        from lovktv.oss import publish_song

        names = publish_song(song_id)
        return {"id": song_id, "ok": True, "published": names}
    return {"id": song_id, "ok": True, "published": []}


def restore_many(song_ids: list[str] | None = None, force: bool = False, publish: bool = True) -> list[dict]:
    ids = song_ids or [row["id"] for row in list_songs()]
    results = []
    for song_id in ids:
        try:
            results.append(restore_song(song_id, force=force, publish=publish))
        except Exception as exc:  # noqa: BLE001
            results.append({"id": song_id, "ok": False, "reason": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore romaji Japanese lyrics via the JA agent")
    parser.add_argument("song_ids", nargs="*", help="Song ids; default is every ja song with romaji")
    parser.add_argument("--all", action="store_true", help="Scan the whole catalog")
    parser.add_argument("--force", action="store_true", help="Re-annotate even without romaji lines")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()
    ids = None if args.all or not args.song_ids else args.song_ids
    results = restore_many(ids, force=args.force, publish=not args.no_publish)
    restored = 0
    for item in results:
        status = "ok" if item.get("ok") else item.get("reason") or "fail"
        print(f"{item['id']} {status}", flush=True)
        restored += int(bool(item.get("ok")))
    print(f"restored {restored}/{len(results)}", flush=True)
    return 0 if restored or not results else 1


if __name__ == "__main__":
    raise SystemExit(main())
