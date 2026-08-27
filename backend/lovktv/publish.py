"""Upload local playback files to OSS. No-op when OSS is not configured."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from lovktv.config import DB_PATH, MEDIA_DIR
from lovktv.oss import oss_ready, publish_all, publish_song
from lovktv.store import init_db


def upsert_songs(rows: list[dict]) -> int:
    init_db()
    if not rows:
        return 0
    keys = [
        "id",
        "title",
        "artist",
        "language",
        "status",
        "error",
        "audio_source",
        "netease_id",
        "created_at",
    ]
    with sqlite3.connect(DB_PATH) as conn:
        for row in rows:
            values = [row.get(key, "") for key in keys]
            conn.execute(
                """
                INSERT INTO songs (id, title, artist, language, status, error, audio_source, netease_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  title=excluded.title,
                  artist=excluded.artist,
                  language=excluded.language,
                  status=excluded.status,
                  error=excluded.error,
                  audio_source=excluded.audio_source,
                  netease_id=excluded.netease_id
                """,
                values,
            )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish lov-ktv media to OSS")
    parser.add_argument("--songs-json", help="Upsert catalog rows from a JSON dump")
    parser.add_argument("song_ids", nargs="*", help="Song ids; default is every folder in media/")
    args = parser.parse_args()
    if args.songs_json:
        rows = json.loads(Path(args.songs_json).read_text(encoding="utf-8"))
        print(f"catalog {upsert_songs(rows)}", flush=True)
    if not oss_ready():
        print("oss disabled; local only", flush=True)
        return 0
    ids = args.song_ids or None
    result = publish_all(ids)
    for song_id, names in result.items():
        print(f"{song_id} {len(names)} {','.join(names)}", flush=True)
    print(f"published {sum(1 for names in result.values() if names)}/{len(result)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
