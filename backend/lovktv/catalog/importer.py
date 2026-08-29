"""Song import orchestration."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from lovktv.catalog import bilibili
from lovktv.catalog.mugen import (
    pick_vocal_hit,
)

from .audio import *
from .search import BROWSER_UA


def _complete_mugen_audio(
    skeleton: dict[str, Any], out_dir: Path, query: str
) -> dict[str, Any]:
    from lovktv.catalog import fetch as f

    mp3_path = out_dir / "original.mp3"
    if mp3_path.exists() and mp3_path.stat().st_size > 200:
        return skeleton
    title, artist = (
        str(skeleton.get("title") or query),
        str(skeleton.get("artist") or ""),
    )
    short = title.split(" · ", 1)[0].strip() or title
    mtv_path = out_dir / "mtv.mp4"
    audio = skeleton.get("audio") if isinstance(skeleton.get("audio"), dict) else {}
    source = skeleton.get("source") if isinstance(skeleton.get("source"), dict) else {}
    filled = ""
    hit = f.pick_bilibili_mv(short, artist) or f.pick_bilibili_mv(
        f.clean_search_title(short), ""
    )
    if hit and f.try_bilibili_download(str(hit["bvid"]), mp3_path, mtv_path):
        filled = "bilibili"
        source["bvid"] = str(hit["bvid"])
        audio["title"] = str(hit.get("title") or "")
        if mtv_path.exists():
            audio["has_video"] = True
            skeleton["has_video"] = True
    if not filled:
        ok, got_title = f.try_ytdlp_search(
            f"{short} {artist}".strip() or query, mp3_path, "soundcloud"
        )
        if ok:
            filled, audio["title"] = "soundcloud", got_title
    if not filled:
        ok, got_title = f.try_ytdlp_search(
            f"{short} {artist}".strip() or query, mp3_path, "youtube"
        )
        if ok:
            filled, audio["title"] = "youtube", got_title
    if not filled or not mp3_path.exists():
        return skeleton
    audio.update(file="original.mp3", source=f"mugen-{filled}", needs_separate=True)
    skeleton.update(audio=audio, source=source, needs_separate=True)
    (out_dir / "skeleton.json").write_text(
        json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return skeleton


def import_song(
    *, query: str, out_dir: Path, song_id: str | None = None, prefer_ytdlp: bool = False
) -> dict[str, Any]:
    from lovktv.catalog import fetch as f

    out_dir.mkdir(parents=True, exist_ok=True)
    if song_id and f.is_mugen_kid(song_id):
        return f._complete_mugen_audio(
            f.import_mugen_song(song_id, out_dir, query=query), out_dir, query
        )
    if not song_id:
        chosen = pick_vocal_hit(f.search_mugen(query, count=8).get("hits") or [])
        if chosen and chosen.get("id"):
            return f._complete_mugen_audio(
                f.import_mugen_song(str(chosen["id"]), out_dir, query=query),
                out_dir,
                query,
            )
    results = f.search_tonzhon(query)
    chosen: dict[str, Any] | None = None
    if song_id:
        chosen = next(
            (item for item in results if str(item.get("id")) == str(song_id)), None
        ) or {"id": song_id, "name": query, "artist": [], "album": [], "pic": ""}
    elif not results:
        raise RuntimeError(f"tonzhon 没有搜到：{query}")
    else:
        chosen = results[0]
        for item in results:
            if f.is_clean_title(str(item.get("name") or "")):
                chosen = item
                break
    title_name, artist_name = (
        str(chosen.get("name") or query),
        f.flatten_artists(chosen),
    )
    kugou = f.fetch_kugou_lyrics(title_name, artist_name)
    lyric_source, needs_align, language = "netease", True, ""
    if kugou and kugou.get("timeline"):
        from lovktv.pipeline.lyrics import write_subtitles

        timeline = kugou["timeline"]
        write_subtitles(timeline, out_dir)
        (out_dir / "lyrics.lrc").write_text(
            str(kugou.get("lrc") or ""), encoding="utf-8"
        )
        lines = [
            {"ms": int(c["start_ms"]), "text": str(c.get("text") or "")}
            for c in timeline.get("cues") or []
        ]
        lyric_source, needs_align, language = (
            "kugou",
            False,
            str(timeline.get("language") or ""),
        )
    else:
        lyric_id = str(chosen.get("id") or "")
        lrc = f.fetch_lyric(lyric_id) if lyric_id.isdigit() else ""
        if not lrc.strip():
            for song in f._tonzhon_hits(title_name, 5, 1):
                sid = str(song.get("id") or "")
                if sid.isdigit():
                    try:
                        lrc = f.fetch_lyric(sid)
                    except Exception:
                        lrc = ""
                    if lrc.strip():
                        break
        if not lrc.strip():
            raise RuntimeError("歌词为空")
        (out_dir / "lyrics.lrc").write_text(lrc, encoding="utf-8")
        lines = f.parse_lrc(lrc)
    if not lines:
        raise RuntimeError("歌词为空")
    audio_file = None
    audio_source = "none"
    audio_title = ""
    audio_bvid = ""
    has_video = False
    mp3_path, mtv_path = out_dir / "original.mp3", out_dir / "mtv.mp4"
    chosen_id, pic = str(chosen.get("id") or ""), str(chosen.get("pic") or "")
    cached = f.peek_audio_source(chosen_id)
    pinned_bvid = str(
        cached.get("bvid")
        or (chosen_id if bilibili.is_bvid(chosen_id) else "")
        or (song_id if bilibili.is_bvid(song_id or "") else "")
    )
    if pinned_bvid and f.try_bilibili_download(pinned_bvid, mp3_path, mtv_path):
        audio_file, audio_source, audio_title, audio_bvid, has_video = (
            "original.mp3",
            "bilibili",
            str(cached.get("title") or title_name),
            pinned_bvid,
            mtv_path.exists(),
        )
        pic = pic or str(cached.get("cover") or "")
    if (
        audio_file is None
        and cached.get("page")
        and f._ytdlp_download(str(cached["page"]), mp3_path)
    ):
        audio_file, audio_source, audio_title = (
            "original.mp3",
            str(cached.get("provider") or "ytdlp"),
            str(cached.get("title") or ""),
        )
    ytdlp_query = (
        f"{chosen.get('name') or ''} {f.flatten_artists(chosen)}".strip() or query
    )
    if audio_file is None:
        hit = f.pick_bilibili_mv(title_name, artist_name) or f.pick_bilibili_mv(
            f.clean_search_title(title_name), ""
        )
        if hit and f.try_bilibili_download(str(hit["bvid"]), mp3_path, mtv_path):
            audio_file, audio_source, audio_title, audio_bvid, has_video = (
                "original.mp3",
                "bilibili",
                str(hit.get("title") or ""),
                str(hit["bvid"]),
                mtv_path.exists(),
            )
            pic = pic or str(hit.get("pic") or "")
    if audio_file is None:
        ok, got_title = f.try_ytdlp_search(ytdlp_query, mp3_path, "soundcloud")
        if ok:
            audio_file, audio_source, audio_title = (
                "original.mp3",
                "soundcloud",
                got_title,
            )
    if (
        audio_file is None
        and not prefer_ytdlp
        and f.try_netease_download(chosen_id, mp3_path)
    ):
        audio_file, audio_source = "original.mp3", "netease"
    if audio_file is None:
        ok, got_title = f.try_ytdlp_search(ytdlp_query, mp3_path, "youtube")
        if ok:
            audio_file, audio_source, audio_title = "original.mp3", "youtube", got_title
    if has_video:
        lp = out_dir / "lyrics.json"
        if lp.exists():
            try:
                timeline = json.loads(lp.read_text(encoding="utf-8"))
                timeline["native_video"] = True
                lp.write_text(
                    json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except (OSError, json.JSONDecodeError):
                pass
    cover_file = ""
    if pic.startswith("http"):
        try:
            req = urllib.request.Request(pic, headers={"User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if len(data) > 2000:
                (out_dir / "cover.jpg").write_bytes(data)
                cover_file = "cover.jpg"
        except Exception:
            cover_file = ""
    skeleton = {
        "title": f"{chosen.get('name')} · {f.flatten_artists(chosen)}",
        "artist": artist_name,
        "language": language,
        "needs_align": needs_align,
        "source": {
            "provider": "tonzhon.com / netease",
            "netease_id": chosen_id,
            "query": query,
            "lyrics": lyric_source,
            "kugou_id": str((kugou or {}).get("candidate", {}).get("id") or ""),
            "bvid": audio_bvid,
        },
        "audio": {"file": audio_file, "source": audio_source, "title": audio_title},
        "cover": cover_file,
        "has_video": has_video,
        "sentences": [
            {"id": f"s{i}", "timestamp_ms": line["ms"], "raw": line["text"]}
            for i, line in enumerate(lines, 1)
        ],
    }
    (out_dir / "skeleton.json").write_text(
        json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return skeleton
