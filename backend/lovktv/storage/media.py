"""Filesystem-derived metadata for a song's published media."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MEDIA_REV_NAMES = (
    "cover.jpg",
    "guide.m4a",
    "karaoke.m4a",
    "lyrics.ass",
    "lyrics.elrc",
    "lyrics.json",
    "lyrics.lrc",
    "lyrics.manual.lrc",
    "mtv.mp4",
    "original.mp3",
    "skeleton.json",
)


def media_rev(song_id: str, media_dir: Path) -> str:
    folder = media_dir / str(song_id)
    digest = hashlib.sha256()
    found = False
    if folder.is_dir():
        for name in MEDIA_REV_NAMES:
            path = folder / name
            if not path.is_file():
                continue
            found = True
            stat = path.stat()
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
            digest.update(b"\0")
    if found:
        return digest.hexdigest()[:12]
    marker = folder / "oss.json"
    if marker.is_file():
        try:
            return str(
                json.loads(marker.read_text(encoding="utf-8")).get("media_rev") or ""
            )
        except (OSError, json.JSONDecodeError, TypeError):
            return ""
    return ""


def media_flags(song_id: str, media_dir: Path) -> dict[str, Any]:
    folder = media_dir / str(song_id)
    native = False
    for name, key in (("lyrics.json", "native_video"), ("skeleton.json", "has_video")):
        path = folder / name
        if not path.exists():
            continue
        try:
            native = bool(json.loads(path.read_text(encoding="utf-8")).get(key))
        except (OSError, json.JSONDecodeError):
            native = False
        if native:
            break
    if not native:
        native = (folder / "mugen.mp4").exists() or (folder / "mugen.webm").exists()
    flags: dict[str, Any] = {"native_video": native}
    rev = media_rev(song_id, media_dir)
    if rev:
        flags["media_rev"] = rev
    return flags


def with_media_flags(
    song: dict[str, Any] | None, media_dir: Path
) -> dict[str, Any] | None:
    if not song:
        return song
    song_id = str(song.get("song_id") or song.get("id") or "")
    return {**song, **media_flags(song_id, media_dir)} if song_id else song
