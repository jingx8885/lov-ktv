"""Song import orchestration."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, cast

from lovktv.catalog.mugen import (
    import_mugen_song,
    is_mugen_kid,
    pick_vocal_hit,
    search_mugen,
)
from lovktv.pipeline.audio import probe_duration_ms

from .audio import (
    _ytdlp_download,
    extract_mv_mp3,
    peek_audio_source,
    pick_bilibili_mv,
    sync_video_to_audio,
    try_bilibili_download,
    try_netease_download,
    try_ytdlp_search,
)
from .bilibili import is_bvid
from .kugou import fetch_kugou_lyrics, lyric_mismatch_ms
from .lyrics import fetch_lyric, parse_lrc
from .search import (
    BROWSER_UA,
    clean_search_title,
    flatten_artists,
    is_clean_title,
    search_tonzhon,
)

# A word-level Kugou track this close to the media length wins outright;
# beyond it the NetEase LRC candidates compete on the same mismatch scale.
KUGOU_ACCEPT_MS = 8000


def try_bilibili_audio_with_mv_fallback(
    bvid: str, mp3_path: Path, video_path: Path
) -> bool:
    """Prefer a native MV, but keep the song importable if its video expires."""
    if try_bilibili_download(bvid, mp3_path, video_path):
        return True
    return try_bilibili_download(bvid, mp3_path)


# How many NetEase lyric candidates to fetch when the media length is known.
NETEASE_LYRIC_CANDIDATES = 6
# A lyric track that runs substantially past the media is a different edit or
# version.  Shorter tracks are allowed because a recording may have an outro
# after its final sung line; the final timeline is clipped to the media clock.
LYRIC_OVERRUN_TOLERANCE_MS = 20_000


def _pick_lyric_result(
    results: list[dict[str, Any]], target_title: str
) -> dict[str, Any] | None:
    """Prefer an exact song title over album/version-suffixed duplicates.

    NetEase often returns both ``Another Day Of Sun`` and
    ``Another Day Of Sun (From ... Soundtrack)``.  The latter can have a
    different lyric segmentation/clock, so using the first result makes an
    otherwise matching MV look like it has scrambled subtitles.
    """
    target = clean_search_title(target_title).casefold()
    if not target:
        return results[0] if results else None
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, item in enumerate(results):
        title = str(item.get("name") or item.get("title") or "").strip()
        raw = title.casefold()
        cleaned = clean_search_title(title).casefold()
        score = 2 if raw == target else (1 if cleaned == target else 0)
        ranked.append((score, -index, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return ranked[0][2] if ranked else None


def _netease_lyric_ids(
    chosen: dict[str, Any], title_name: str, preferred_id: str = ""
) -> list[str]:
    """Candidate NetEase ids: the chosen song first, then title matches."""
    ids: list[str] = []
    preferred = str(preferred_id or "").strip()
    if preferred.isdigit():
        ids.append(preferred)
    chosen_id = str(chosen.get("id") or "")
    if chosen_id.isdigit() and chosen_id not in ids:
        ids.append(chosen_id)
    try:
        results = search_tonzhon(title_name, count=NETEASE_LYRIC_CANDIDATES, page=1)
    except Exception:
        results = []
    picked = _pick_lyric_result(results, title_name)
    ordered = ([picked] if picked else []) + [
        item for item in results if item is not picked
    ]
    for song in ordered:
        sid = str(song.get("id") or "")
        if sid.isdigit() and sid not in ids:
            ids.append(sid)
    return ids[:NETEASE_LYRIC_CANDIDATES]


def _lrc_last_ms(lines: list[dict[str, Any]]) -> int:
    return max(
        (int(item.get("end_ms") or item.get("ms") or 0) for item in lines),
        default=0,
    )


def _fetch_netease_lyrics(ids: list[str], media_ms: int) -> dict[str, Any] | None:
    """Fetch LRC candidates and keep the one that fits the media length best.

    Without a known media length the first candidate with lyrics wins, as
    before.  With one, every candidate is scored by ``lyric_mismatch_ms`` so
    a film cut picks the film lyrics even when the studio single is listed
    first.
    """
    best: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = []
    for sid in ids:
        try:
            lrc = fetch_lyric(sid)
        except Exception:
            continue
        if not lrc.strip():
            continue
        lines = parse_lrc(lrc)
        if not lines:
            continue
        last_ms = _lrc_last_ms(lines)
        if media_ms and last_ms > media_ms + LYRIC_OVERRUN_TOLERANCE_MS:
            # Do not silently attach the studio/full-song LRC to a short film
            # cut (or only the first page of a multi-page Bilibili video).
            continue
        mismatch = lyric_mismatch_ms(last_ms, media_ms) if media_ms else 0
        candidate = {"id": sid, "lrc": lrc, "lines": lines, "mismatch_ms": mismatch}
        candidates.append(candidate)
        if best is None or mismatch < int(best["mismatch_ms"]):
            best = candidate
        if mismatch == 0:
            break
    if best is not None:
        # Keep the alternatives for the post-separation energy check.  The
        # selected candidate remains at the top-level for compatibility with
        # existing callers and persisted skeletons.
        best["candidates"] = [
            {key: value for key, value in item.items() if key != "candidates"}
            for item in candidates
        ]
    return best


def _select_lyrics(
    title_name: str,
    artist_name: str,
    chosen: dict[str, Any],
    media_ms: int,
    preferred_lyric_id: str = "",
) -> dict[str, Any]:
    """Choose between Kugou KRC and NetEase LRC using the media length."""
    kugou = fetch_kugou_lyrics(title_name, artist_name, duration_ms=media_ms)
    if kugou and not kugou.get("timeline"):
        kugou = None
    if kugou is not None and media_ms and "mismatch_ms" not in kugou:
        cues = kugou["timeline"].get("cues") or []
        last_ms = max(
            (int(c.get("end_ms") or c.get("start_ms") or 0) for c in cues), default=0
        )
        kugou["mismatch_ms"] = lyric_mismatch_ms(
            last_ms, media_ms, int(kugou.get("duration_ms") or 0)
        )
    kugou_mismatch = int((kugou or {}).get("mismatch_ms") or 0)
    if kugou is not None and (not media_ms or kugou_mismatch <= KUGOU_ACCEPT_MS):
        return {"source": "kugou", "kugou": kugou, "mismatch_ms": kugou_mismatch}
    netease = _fetch_netease_lyrics(
        _netease_lyric_ids(chosen, title_name, preferred_lyric_id), media_ms
    )
    if netease is not None and (
        kugou is None or int(netease["mismatch_ms"]) < kugou_mismatch
    ):
        return {
            "source": "netease",
            "netease": netease,
            "mismatch_ms": int(netease["mismatch_ms"]),
        }
    if kugou is not None:
        return {"source": "kugou", "kugou": kugou, "mismatch_ms": kugou_mismatch}
    if netease is not None:
        return {
            "source": "netease",
            "netease": netease,
            "mismatch_ms": int(netease["mismatch_ms"]),
        }
    raise RuntimeError("歌词为空")


def _complete_mugen_audio(
    skeleton: dict[str, Any], out_dir: Path, query: str
) -> dict[str, Any]:
    mp3_path = out_dir / "original.mp3"
    if mp3_path.exists() and mp3_path.stat().st_size > 200:
        # A Mugen import can already contain both files.  Keep the MP3 as the
        # master clock even on this fast path (the previous implementation
        # returned before normalising the official MV duration/audio track).
        mtv_path = out_dir / "mtv.mp4"
        if mtv_path.exists():
            sync_video_to_audio(mtv_path, mp3_path)
        return skeleton
    title, artist = (
        str(skeleton.get("title") or query),
        str(skeleton.get("artist") or ""),
    )
    short = title.split(" · ", 1)[0].strip() or title
    mtv_path = out_dir / "mtv.mp4"
    audio_value = skeleton.get("audio")
    source_value = skeleton.get("source")
    audio = cast(dict[str, Any], audio_value) if isinstance(audio_value, dict) else {}
    source = (
        cast(dict[str, Any], source_value) if isinstance(source_value, dict) else {}
    )
    filled = ""
    hit = pick_bilibili_mv(short, artist) or pick_bilibili_mv(
        clean_search_title(short), ""
    )
    if hit and try_bilibili_audio_with_mv_fallback(str(hit["bvid"]), mp3_path, mtv_path):
        filled = "bilibili"
        source["bvid"] = str(hit["bvid"])
        audio["title"] = str(hit.get("title") or "")
        if mtv_path.exists():
            audio["has_video"] = True
            skeleton["has_video"] = True
    if not filled:
        ok, got_title = try_ytdlp_search(
            f"{short} {artist}".strip() or query, mp3_path, "soundcloud"
        )
        if ok:
            filled, audio["title"] = "soundcloud", got_title
    if not filled:
        ok, got_title = try_ytdlp_search(
            f"{short} {artist}".strip() or query, mp3_path, "youtube"
        )
        if ok:
            filled, audio["title"] = "youtube", got_title
    if not filled or not mp3_path.exists():
        return skeleton
    if mtv_path.exists():
        sync_video_to_audio(mtv_path, mp3_path)
    audio.update(file="original.mp3", source=f"mugen-{filled}", needs_separate=True)
    skeleton.update(audio=audio, source=source, needs_separate=True)
    (out_dir / "skeleton.json").write_text(
        json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return skeleton


def import_song(
    *,
    query: str,
    out_dir: Path,
    song_id: str | None = None,
    prefer_ytdlp: bool = False,
    title_hint: str = "",
    artist_hint: str = "",
    lyric_id: str = "",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if song_id and is_mugen_kid(song_id):
        return _complete_mugen_audio(
            import_mugen_song(song_id, out_dir, query=query), out_dir, query
        )
    if not song_id:
        chosen = pick_vocal_hit(search_mugen(query, count=8).get("hits") or [])
        if chosen and chosen.get("id"):
            return _complete_mugen_audio(
                import_mugen_song(str(chosen["id"]), out_dir, query=query),
                out_dir,
                query,
            )
    # External search hits (notably Bilibili) carry a title/artist that can
    # differ from the user's broad query.  Use that exact hit metadata for
    # lyric lookup; otherwise a second search may select a different version.
    lookup_query = (
        " ".join(
            part.strip() for part in (title_hint, artist_hint) if part and part.strip()
        )
        or query
    )
    results = search_tonzhon(lookup_query)
    chosen: dict[str, Any] | None = None
    if song_id:
        matched = next(
            (item for item in results if str(item.get("id")) == str(song_id)), None
        )
        if matched:
            chosen = matched
        else:
            # Keep the media id pinned to the selected hit (for the audio
            # cache/BVID), while borrowing only descriptive metadata from the
            # closest lyric search result.
            lyric_hint = _pick_lyric_result(results, title_hint or query)
            chosen = {
                "id": song_id,
                "name": title_hint or (lyric_hint or {}).get("name") or query,
                "artist": (lyric_hint or {}).get("artist")
                or ([artist_hint] if artist_hint else []),
                "album": (lyric_hint or {}).get("album") or [],
                "pic": (lyric_hint or {}).get("pic") or "",
            }
    elif not results:
        raise RuntimeError(f"tonzhon 没有搜到：{query}")
    else:
        chosen = results[0]
        for item in results:
            if is_clean_title(str(item.get("name") or "")):
                chosen = item
                break
    title_name, artist_name = (
        str(chosen.get("name") or title_hint or query),
        flatten_artists(chosen) or artist_hint,
    )

    # Media first: the lyric version is chosen against the length of what we
    # will actually play (a film cut and the studio single share a title).
    audio_file = None
    audio_source = "none"
    audio_title = ""
    audio_bvid = ""
    has_video = False
    mp3_path, mtv_path = out_dir / "original.mp3", out_dir / "mtv.mp4"
    chosen_id, pic = str(chosen.get("id") or ""), str(chosen.get("pic") or "")
    cached = peek_audio_source(chosen_id)
    pinned_bvid = str(
        cached.get("bvid")
        or (chosen_id if is_bvid(chosen_id) else "")
        or (song_id if is_bvid(song_id or "") else "")
    )
    if pinned_bvid and try_bilibili_audio_with_mv_fallback(pinned_bvid, mp3_path, mtv_path):
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
        and _ytdlp_download(str(cached["page"]), mp3_path)
    ):
        audio_file, audio_source, audio_title = (
            "original.mp3",
            str(cached.get("provider") or "ytdlp"),
            str(cached.get("title") or ""),
        )
    ytdlp_query = (
        f"{chosen.get('name') or ''} {flatten_artists(chosen)}".strip() or query
    )
    if audio_file is None:
        hit = pick_bilibili_mv(title_name, artist_name) or pick_bilibili_mv(
            clean_search_title(title_name), ""
        )
        if hit and try_bilibili_audio_with_mv_fallback(str(hit["bvid"]), mp3_path, mtv_path):
            audio_file, audio_source, audio_title, audio_bvid, has_video = (
                "original.mp3",
                "bilibili",
                str(hit.get("title") or ""),
                str(hit["bvid"]),
                mtv_path.exists(),
            )
            pic = pic or str(hit.get("pic") or "")
    if audio_file is None:
        ok, got_title = try_ytdlp_search(ytdlp_query, mp3_path, "soundcloud")
        if ok:
            audio_file, audio_source, audio_title = (
                "original.mp3",
                "soundcloud",
                got_title,
            )
    if (
        audio_file is None
        and not prefer_ytdlp
        and try_netease_download(chosen_id, mp3_path)
    ):
        audio_file, audio_source = "original.mp3", "netease"
    if audio_file is None:
        ok, got_title = try_ytdlp_search(ytdlp_query, mp3_path, "youtube")
        if ok:
            audio_file, audio_source, audio_title = "original.mp3", "youtube", got_title
    mv_audio_extracted = False
    if has_video:
        # Prefer the MV's own full mix. The downloaded audio remains the
        # fallback for video-only sources.
        mv_audio_extracted = extract_mv_mp3(mtv_path, mp3_path)
        sync_video_to_audio(mtv_path, mp3_path)
    media_ms = probe_duration_ms(mp3_path) or (
        probe_duration_ms(mtv_path) if has_video else 0
    )

    selected = _select_lyrics(
        title_name, artist_name, chosen, media_ms, preferred_lyric_id=lyric_id
    )
    lyric_source = str(selected["source"])
    kugou = selected.get("kugou")
    needs_align, language = True, ""
    if lyric_source == "kugou" and kugou:
        from lovktv.pipeline.lyrics import write_subtitles

        timeline = kugou["timeline"]
        if has_video:
            timeline["native_video"] = True
        write_subtitles(timeline, out_dir)
        (out_dir / "lyrics.lrc").write_text(
            str(kugou.get("lrc") or ""), encoding="utf-8"
        )
        lines = [
            {"ms": int(c["start_ms"]), "text": str(c.get("text") or "")}
            for c in timeline.get("cues") or []
        ]
        needs_align, language = False, str(timeline.get("language") or "")
    else:
        netease = selected["netease"]
        (out_dir / "lyrics.lrc").write_text(str(netease["lrc"]), encoding="utf-8")
        lines = list(netease["lines"])
    if not lines:
        raise RuntimeError("歌词为空")

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
        "title": f"{chosen.get('name')} · {flatten_artists(chosen)}",
        "artist": artist_name,
        "language": language,
        "needs_align": needs_align,
        "source": {
            "provider": "tonzhon.com / netease",
            "netease_id": chosen_id,
            "query": query,
            "lyrics": lyric_source,
            "lyric_id": str((selected.get("netease") or {}).get("id") or ""),
            "kugou_id": str((kugou or {}).get("candidate", {}).get("id") or ""),
            "media_ms": media_ms,
            "lyric_mismatch_ms": int(selected.get("mismatch_ms") or 0),
            "bvid": audio_bvid,
            # Non-Mugen video imports may need to choose another lyric clock
            # after vocal separation.  Persist the fetched alternatives so
            # the worker can score them against real vocal energy.
            "lyric_candidates": [
                {
                    "id": str(item.get("id") or ""),
                    "lrc": str(item.get("lrc") or ""),
                    "mismatch_ms": int(item.get("mismatch_ms") or 0),
                }
                for item in ((selected.get("netease") or {}).get("candidates") or [])
                if isinstance(item, dict) and str(item.get("lrc") or "").strip()
            ],
        },
        "audio": {
            "file": audio_file,
            "source": audio_source,
            "title": audio_title,
            "mv_audio_extracted": mv_audio_extracted,
        },
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
