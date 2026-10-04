"""Repair karaoke fills that stop ~1 second after the line starts.

Timelines written before the sing-end walk merged vocal phrases keep the
line on screen until the next cue, but the per-word sweep dies almost
immediately because the stored token span was cut at the first fragmented
energy island.  A bare run reports affected cues; ``--fix`` re-packs token
timing against the stored vocal stem, rewrites subtitles, and republishes.

    python -m lovktv.workers.lyric_fill            # report only
    python -m lovktv.workers.lyric_fill --fix      # repack + republish
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lovktv.core.config import MEDIA_DIR
from lovktv.pipeline.audio import extract_envelope, vocal_regions
from lovktv.pipeline.bounds import line_sing_end, pack_tokens_to_singing
from lovktv.pipeline.lyrics import write_subtitles
from lovktv.storage.store import get_song, list_songs

# Mirrors restore_ja.pack_timeline_to_voice: separated vocals first, then the
# audible mixes a fill may legitimately ride on.
AUDIO_CANDIDATES = ("vocals.wav", "guide.m4a", "karaoke.m4a", "original.mp3")
# Re-pack a cue only when the stored sweep ends this much earlier than the
# singing the current logic measures; smaller gaps are ordinary short lines.
EARLY_FILL_GAP_MS = 600


def _vocal_envelope(out_dir: Path) -> tuple[list[float], int] | None:
    for name in AUDIO_CANDIDATES:
        path = out_dir / name
        if not path.exists():
            continue
        envelope, hop_ms = extract_envelope(path)
        if envelope:
            return envelope, hop_ms
    return None


def early_fill_cues(
    cues: list[dict[str, Any]] | None,
    regions: list[tuple[int, int]],
) -> list[int]:
    """Cue indexes whose stored sweep ends well before the measured singing."""
    flagged: list[int] = []
    for index, cue in enumerate(cues or []):
        tokens = cue.get("tokens") or []
        if not tokens:
            continue
        start_ms = int(cue.get("start_ms") or 0)
        display_end = int(cue.get("end_ms") or start_ms)
        stored_end = int(tokens[-1].get("end_ms") or start_ms)
        sing_end = line_sing_end(start_ms, display_end, regions)
        if sing_end - stored_end >= EARLY_FILL_GAP_MS:
            flagged.append(index)
    return flagged


def inspect_song(
    song_id: str,
) -> tuple[dict[str, Any], Path | None, dict[str, Any] | None]:
    song = get_song(song_id) or {}
    report: dict[str, Any] = {
        "id": song_id,
        "title": song.get("title") or "",
        "artist": song.get("artist") or "",
        "ok": True,
    }
    out_dir = MEDIA_DIR / song_id
    path = out_dir / "lyrics.json"
    if not path.exists():
        report["skipped"] = "no-lyrics"
        return report, None, None
    try:
        timeline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report["ok"] = False
        report["error"] = f"lyrics.json unreadable: {exc}"
        return report, out_dir, None
    audio = _vocal_envelope(out_dir)
    if audio is None:
        report["skipped"] = "no-audio"
        return report, out_dir, timeline
    envelope, hop_ms = audio
    regions = vocal_regions(envelope, hop_ms)
    flagged = early_fill_cues(timeline.get("cues"), regions)
    report["early_fill"] = len(flagged)
    report["cues"] = len(timeline.get("cues") or [])
    return report, out_dir, timeline


def repair_song(song_id: str, publish: bool = True) -> dict[str, Any]:
    report, out_dir, timeline = inspect_song(song_id)
    if not report.get("early_fill") or timeline is None or out_dir is None:
        return report
    pack_tokens_to_singing(timeline.get("cues") or [], *_vocal_envelope(out_dir))
    write_subtitles(timeline, out_dir)
    published: list[str] = []
    if publish:
        from lovktv.media.oss import publish_song

        published = publish_song(song_id)
    report["changed"] = True
    report["actions"] = ["repacked-fill"]
    report["published"] = published
    return report


def run(
    song_ids: list[str] | None = None,
    fix: bool = False,
    publish: bool = True,
) -> list[dict[str, Any]]:
    ids = song_ids or [str(row["id"]) for row in list_songs()]
    results: list[dict[str, Any]] = []
    for song_id in ids:
        try:
            results.append(repair_song(song_id, publish=publish) if fix else inspect_song(song_id)[0])
        except Exception as exc:  # noqa: BLE001
            results.append({"id": song_id, "ok": False, "error": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report / repair karaoke fills that end ~1s into the line"
    )
    parser.add_argument("song_ids", nargs="*", help="Song ids; default is the whole catalog")
    parser.add_argument("--fix", action="store_true", help="Repack and republish affected songs")
    parser.add_argument("--no-publish", action="store_true", help="Do not upload to OSS after fixing")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    parser.add_argument("--all", action="store_true", help="Also list songs that are fine")
    args = parser.parse_args()
    results = run(
        args.song_ids or None, fix=args.fix, publish=not args.no_publish
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            flag = item.get("early_fill") or 0
            if not flag and not item.get("error") and not args.all:
                continue
            label = f"{item.get('title') or ''} · {item.get('artist') or ''}".strip(" ·")
            if item.get("error"):
                status = f"ERROR {item['error']}"
            elif flag:
                status = f"early_fill {flag}/{item.get('cues') or 0}"
                if item.get("changed"):
                    status += " <- " + ",".join(item.get("actions") or ["-"])
            else:
                status = "ok"
            print(f"{item['id']} {status:<40} {label}", flush=True)
    bad = [item for item in results if not item.get("ok")]
    flagged = sum(1 for item in results if item.get("early_fill"))
    fixed = sum(1 for item in results if item.get("changed"))
    print(
        f"songs {len(results)} early_fill {flagged}"
        + (f" fixed {fixed}" if args.fix else "")
        + (f" errors {len(bad)}" if bad else ""),
        flush=True,
    )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
