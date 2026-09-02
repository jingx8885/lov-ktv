"""Karaoke Mugen (kara.moe) search + download.

Official ASS lyrics are already karaoke-timed. Original MP4 is the
background; TV overlays our lyrics.

Audio for 原唱/伴奏:
- dual-track → extract karaoke + vocal
- single-mix MP4 → ONNX separate
- off-vocal only → keep as 伴奏, fetch the vocal sibling as 原唱
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from lovktv.catalog.http import outbound_proxy, urlopen

MUGEN_HOST = "https://kara.moe"
MUGEN_SEARCH = f"{MUGEN_HOST}/api/karas/search"
MUGEN_KARA = f"{MUGEN_HOST}/api/karas/{{kid}}"
MUGEN_MEDIA = f"{MUGEN_HOST}/downloads/medias/{{name}}"
MUGEN_LYRICS = f"{MUGEN_HOST}/downloads/lyrics/{{name}}"
MUGEN_KID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
ASS_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{1,3})$")
K_TAG = re.compile(r"\\k[fo]?(\d+(?:\.\d+)?)", re.I)
OVERRIDE = re.compile(r"(\{[^}]*\})")
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
LANG_MAP = {
    "jpn": "ja",
    "ja": "ja",
    "eng": "en",
    "en": "en",
    "chi": "zh",
    "zho": "zh",
    "cmn": "zh",
    "yue": "zh",
    "zh": "zh",
    "kor": "ko",
    "ko": "ko",
}
KARAOKE_HINTS = (
    "instrumental",
    "karaoke",
    "off vocal",
    "off-vocal",
    "inst",
    "no vocal",
)
VOCAL_HINTS = ("vocal", "guide", "original", "full", "with vocal")
OFF_VOCAL_MARKERS = (
    "off vocal",
    "off-vocal",
    "offvocal",
    "no vocal",
    "オフボーカル",
    "instrumental",
    "karaoke",
    "カラオケ",
    "伴奏",
)


def is_mugen_kid(value: str | None) -> bool:
    return bool(value and MUGEN_KID.match(str(value).strip()))


def _request(url: str, timeout: float = 20) -> urllib.request.Request:
    host = (
        urllib.parse.urlparse(url).scheme
        + "://"
        + (urllib.parse.urlparse(url).netloc or "kara.moe")
    )
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "*/*",
            "Referer": host + "/",
        },
    )


def get_json(url: str, timeout: float = 20, via_proxy: bool = False) -> Any:
    with urlopen(_request(url), timeout=timeout, via_proxy=via_proxy) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_file(
    url: str,
    dest: Path,
    timeout: float = 600,
    min_size: int = 200,
    via_proxy: bool = False,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with (
            urlopen(_request(url), timeout=timeout, via_proxy=via_proxy) as resp,
            tmp.open("wb") as handle,
        ):
            shutil.copyfileobj(resp, handle)
        if tmp.stat().st_size < min_size:
            raise RuntimeError(f"下载太小：{url}")
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def download_file_resilient(
    url: str, dest: Path, timeout: float = 60, min_size: int = 200
) -> None:
    try:
        download_file(url, dest, timeout=timeout, min_size=min_size, via_proxy=False)
        return
    except Exception:
        if not outbound_proxy():
            raise
    download_file(url, dest, timeout=timeout, min_size=min_size, via_proxy=True)


def pick_title(item: dict[str, Any]) -> str:
    titles = item.get("titles") if isinstance(item.get("titles"), dict) else {}
    for key in ("jpn", "chi", "zho", "cmn"):
        if titles.get(key):
            return str(titles[key])
    default = str(item.get("titles_default_language") or "")
    if default and titles.get(default):
        return str(titles[default])
    for key in ("eng", "qro"):
        if titles.get(key):
            return str(titles[key])
    for value in titles.values():
        if value:
            return str(value)
    return str(item.get("songname") or "")


def _tag_names(item: dict[str, Any], key: str) -> list[str]:
    out: list[str] = []
    for tag in item.get(key) or []:
        if isinstance(tag, dict) and tag.get("name"):
            out.append(str(tag["name"]))
        elif tag:
            out.append(str(tag))
    return out


def pick_artist(item: dict[str, Any]) -> str:
    names = _tag_names(item, "singergroups") + _tag_names(item, "singers")
    if names:
        return " / ".join(names)
    series = _tag_names(item, "series")
    return " / ".join(series)


def pick_album(item: dict[str, Any]) -> str:
    series = _tag_names(item, "series")
    kinds = _tag_names(item, "songtypes")
    bits = [part for part in ((*series[:1], *kinds[:1])) if part]
    return " · ".join(bits)


def is_off_vocal(*parts: str) -> bool:
    text = " ".join(part for part in parts if part).lower()
    return any(mark in text for mark in OFF_VOCAL_MARKERS)


def pick_vocal_hit(hits: list[dict[str, Any]]) -> dict[str, Any] | None:
    vocal = next(
        (hit for hit in hits if hit.get("id") and not hit.get("off_vocal")), None
    )
    if vocal:
        return vocal
    return next((hit for hit in hits if hit.get("id")), None)


def pick_language(item: dict[str, Any]) -> str:
    for name in _tag_names(item, "langs"):
        mapped = LANG_MAP.get(name.lower())
        if mapped:
            return mapped
    return ""


def map_hit(item: dict[str, Any]) -> dict[str, Any]:
    kid = str(item.get("kid") or "")
    title = pick_title(item)
    songname = str(item.get("songname") or title)
    lyrics = bool(item.get("lyrics_infos"))
    off_vocal = is_off_vocal(songname, title)
    return {
        "id": kid,
        "title": title,
        "artist": pick_artist(item),
        "album": pick_album(item),
        "pic": "",
        "source": "mugen",
        "is_mv": True,
        "language": pick_language(item) or "ja",
        "clean": not off_vocal,
        "off_vocal": off_vocal,
        "preview_url": f"/api/preview/{kid}" if kid else "",
        "lyrics_ready": lyrics,
        "duration": int(item.get("duration") or 0),
        "media": str(item.get("mediafile") or ""),
        "songname": songname,
    }


def _empty_search(query: str, page: int, count: int) -> dict[str, Any]:
    return {
        "query": query,
        "page": page,
        "count": count,
        "has_more": False,
        "hits": [],
        "total": 0,
    }


def _search_mugen_api(query: str, count: int, page: int) -> dict[str, Any]:
    start = (page - 1) * count
    params = urllib.parse.urlencode({"filter": query, "from": start, "size": count})
    data = get_json(f"{MUGEN_SEARCH}?{params}", timeout=5)
    content = data.get("content") if isinstance(data, dict) else []
    infos = data.get("infos") if isinstance(data, dict) else {}
    hits = [
        map_hit(item)
        for item in content or []
        if isinstance(item, dict) and item.get("kid")
    ]
    hits.sort(key=lambda hit: (bool(hit.get("off_vocal")), str(hit.get("title") or "")))
    total = int((infos or {}).get("count") or len(hits))
    return {
        "query": query,
        "page": page,
        "count": count,
        "has_more": total > start + len(hits),
        "hits": hits,
        "total": total,
    }


def search_mugen(query: str, count: int = 10, page: int = 1) -> dict[str, Any]:
    from lovktv.catalog import mugen_index

    page = max(1, int(page))
    count = max(1, min(int(count), 30))
    items = mugen_index.cached_items()
    if not items:
        items = mugen_index.ensure_index(wait=25)
    if items:
        result = mugen_index.search_items(items, query, count, page)
        result["hits"] = [
            map_hit(mugen_index.item_to_kara(item)) for item in result["hits"]
        ]
        return result
    try:
        return _search_mugen_api(query, count, page)
    except Exception as exc:
        print(f"[lovktv] mugen search api failed: {exc}", flush=True)
        return _empty_search(query, page, count)


def open_mugen_preview(kid: str, media_name: str = ""):
    if not is_mugen_kid(kid):
        return None
    name = str(media_name or "").strip()
    if not name:
        try:
            kara = fetch_kara(kid)
        except Exception:
            kara = {}
        name = str((kara or {}).get("mediafile") or "")
    urls = [f"{MUGEN_HOST}/previews/{kid}.mp3"]
    if name:
        urls.append(MUGEN_MEDIA.format(name=urllib.parse.quote(name)))
    for url in urls:
        try:
            return urllib.request.urlopen(_request(url), timeout=30)
        except Exception:
            continue
    return None


def fetch_kara(kid: str) -> dict[str, Any]:
    from lovktv.catalog import mugen_index

    item = mugen_index.find_item(kid)
    if item:
        return mugen_index.item_to_kara(item)
    try:
        raw = mugen_index.fetch_kara_json(kid)
        item = mugen_index.kara_to_item(raw, {})
        if item:
            return mugen_index.item_to_kara(item)
    except Exception:
        pass
    try:
        data = get_json(MUGEN_KARA.format(kid=kid), timeout=12)
    except Exception as exc:
        raise RuntimeError(f"Karaoke Mugen 没有这首：{kid}") from exc
    if not isinstance(data, dict) or not data.get("kid"):
        raise RuntimeError(f"Karaoke Mugen 没有这首：{kid}")
    return data


def parse_ass_time(raw: str) -> int:
    match = ASS_TIME.match((raw or "").strip())
    if not match:
        return 0
    hours, minutes, seconds, frac = match.groups()
    milli = int((frac + "000")[:3])
    return int(hours) * 3_600_000 + int(minutes) * 60_000 + int(seconds) * 1000 + milli


def _decode_ass(text: str) -> str:
    return (
        text.replace("\\N", " ")
        .replace("\\n", " ")
        .replace("\\h", " ")
        .replace("\\{", "{")
        .replace("\\}", "}")
    )


def tokens_from_ass_text(start_ms: int, raw: str) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    cursor = start_ms
    pending_ms: int | None = None
    for part in OVERRIDE.split(raw or ""):
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            found = None
            for match in K_TAG.finditer(part):
                found = max(10, int(round(float(match.group(1)) * 10)))
            if found is not None:
                if pending_ms is not None:
                    cursor += pending_ms
                pending_ms = found
            continue
        text = _decode_ass(part)
        if pending_ms is None:
            if text.strip() and tokens:
                tokens[-1]["text"] += text
                tokens[-1]["end_ms"] = max(tokens[-1]["end_ms"], cursor)
            continue
        duration = pending_ms
        pending_ms = None
        end_ms = cursor + duration
        if text.strip():
            tokens.append(
                {
                    "text": text,
                    "start_ms": cursor,
                    "end_ms": end_ms,
                    "reading": "",
                }
            )
        cursor = end_ms
    return tokens


def _event_fields(line: str) -> tuple[str, list[str]] | None:
    if ":" not in line:
        return None
    kind, rest = line.split(":", 1)
    fields = rest.split(",", 9)
    if len(fields) < 10:
        return None
    return kind.strip(), fields


def parse_ass(raw: str) -> list[dict[str, Any]]:
    """Turn KM ASS karaoke into lov-ktv cues. Prefer Dialogue; fall back to Comment karaoke."""
    dialogue: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    text = (raw or "").lstrip("\ufeff")
    for line in text.splitlines():
        parsed = _event_fields(line)
        if not parsed:
            continue
        kind, fields = parsed
        if kind not in {"Dialogue", "Comment"}:
            continue
        effect = fields[8].strip().lower()
        if kind == "Comment" and effect in {"template", "code"}:
            continue
        if kind == "Comment" and "template" in effect:
            continue
        start_ms = parse_ass_time(fields[1])
        end_ms = parse_ass_time(fields[2])
        body = fields[9]
        had_k = bool(K_TAG.search(body))
        tokens = tokens_from_ass_text(start_ms, body)
        if tokens:
            start_ms = tokens[0]["start_ms"]
            end_ms = max(end_ms, tokens[-1]["end_ms"])
            line_text = "".join(str(token["text"]) for token in tokens).strip()
        else:
            line_text = OVERRIDE.sub("", _decode_ass(body)).strip()
            if line_text:
                tokens = [
                    {
                        "text": line_text,
                        "start_ms": start_ms,
                        "end_ms": max(end_ms, start_ms + 200),
                        "reading": "",
                    }
                ]
        if not line_text:
            continue
        cue = {
            "text": line_text,
            "start_ms": start_ms,
            "end_ms": max(end_ms, start_ms + 200),
            "tokens": tokens,
            "karaoke": had_k,
        }
        if kind == "Dialogue":
            dialogue.append(cue)
        elif effect == "karaoke" or had_k:
            comments.append(cue)
    karaoke_dialogue = [cue for cue in dialogue if cue.get("karaoke")]
    chosen = karaoke_dialogue or comments or dialogue
    dedup: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for cue in chosen:
        key = (int(cue["start_ms"]), str(cue["text"]))
        if key in seen:
            continue
        seen.add(key)
        cue.pop("karaoke", None)
        dedup.append(cue)
    dedup.sort(key=lambda item: (item["start_ms"], item["end_ms"]))
    return dedup


def timeline_from_ass(raw: str, language: str = "ja") -> dict[str, Any]:
    from lovktv.pipeline.lyrics import merge_english_token_chunks

    cues = parse_ass(raw)
    if not cues:
        raise RuntimeError("Karaoke Mugen 歌词是空的")
    if str(language or "").strip().lower() == "en":
        for cue in cues:
            cue["tokens"] = merge_english_token_chunks(cue.get("tokens") or [])
    return {
        "language": language or "ja",
        "alignment": "mugen",
        "alignment_source": "karaoke-mugen",
        "cues": cues,
    }


def lrc_from_cues(cues: list[dict[str, Any]]) -> str:
    lines = []
    for cue in cues:
        ms = int(cue.get("start_ms") or 0)
        minutes, rem = divmod(ms, 60_000)
        seconds, milli = divmod(rem, 1000)
        lines.append(
            f"[{minutes:02d}:{seconds:02d}.{milli:03d}]{cue.get('text') or ''}"
        )
    return "\n".join(lines) + "\n"


def _ffmpeg(*args: str, timeout: int = 300) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("需要 ffmpeg")
    subprocess.run(
        ["ffmpeg", "-y", *args], check=True, timeout=timeout, capture_output=True
    )


def probe_streams(path: Path) -> list[dict[str, Any]]:
    if not shutil.which("ffprobe"):
        return []
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return []
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    return [item for item in streams if isinstance(item, dict)]


def _stream_label(stream: dict[str, Any]) -> str:
    tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
    return " ".join(
        str(tags.get(key) or "") for key in ("title", "handler_name", "language")
    ).lower()


def classify_dual_audio(streams: list[dict[str, Any]]) -> dict[str, int] | None:
    audios = [item for item in streams if item.get("codec_type") == "audio"]
    if len(audios) < 2:
        return None
    karaoke = None
    vocal = None
    for item in audios:
        label = _stream_label(item)
        if any(hint in label for hint in KARAOKE_HINTS):
            karaoke = item
        elif any(hint in label for hint in VOCAL_HINTS):
            vocal = item
    if karaoke is None:
        karaoke = audios[0]
    if vocal is None:
        vocal = next((item for item in audios if item is not karaoke), audios[-1])
    return {"karaoke": int(karaoke["index"]), "vocal": int(vocal["index"])}


def extract_audio(src: Path, dest: Path, stream_index: int | None = None) -> None:
    from lovktv.pipeline.loudness import loudnorm_args

    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(src)]
    if stream_index is not None:
        args += ["-map", f"0:{stream_index}"]
    else:
        args += ["-map", "0:a:0?"]
    if dest.suffix.lower() == ".wav":
        args += ["-acodec", "pcm_s16le", str(dest)]
    elif dest.suffix.lower() == ".m4a":
        args += [*loudnorm_args(), "-c:a", "aac", "-b:a", "192k", str(dest)]
    else:
        args += [*loudnorm_args(), "-c:a", "libmp3lame", "-q:a", "2", str(dest)]
    _ffmpeg(*args)


def video_codec(path: Path) -> str:
    for stream in probe_streams(path):
        if stream.get("codec_type") == "video":
            return str(stream.get("codec_name") or "").lower()
    return ""


def install_video(src: Path, dest: Path) -> bool:
    if src.suffix.lower() not in {".mp4", ".mkv", ".webm", ".mov"}:
        return False
    codec = video_codec(src)
    try:
        if codec in {"h264", "avc1"} and src.suffix.lower() == ".mp4":
            shutil.copy2(src, dest)
        elif codec in {"h264", "avc1"}:
            _ffmpeg("-i", str(src), "-map", "0:v:0", "-c:v", "copy", "-an", str(dest))
        else:
            _ffmpeg(
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                "-an",
                str(dest),
                timeout=600,
            )
        return dest.exists() and dest.stat().st_size > 1000
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def prepare_media(src: Path, out_dir: Path) -> dict[str, Any]:
    """Extract audio; keep official video as mtv.mp4 when present.

    Dual-track files skip ONNX. Single-mix files still need separation.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    original = out_dir / "original.mp3"
    streams = probe_streams(src)
    dual = classify_dual_audio(streams)
    video = any(
        item.get("codec_type") == "video" for item in streams
    ) or src.suffix.lower() in {".mp4", ".mkv", ".webm"}
    if dual:
        from lovktv.pipeline.loudness import loudnorm_args

        extract_audio(src, out_dir / "karaoke.m4a", dual["karaoke"])
        extract_audio(src, out_dir / "vocals.wav", dual["vocal"])
        extract_audio(src, out_dir / "guide.m4a", dual["vocal"])
        try:
            _ffmpeg(
                "-i", str(out_dir / "karaoke.m4a"),
                "-i", str(out_dir / "vocals.wav"),
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=longest:normalize=1[mix]",
                "-map", "[mix]", *loudnorm_args(),
                "-c:a", "libmp3lame", "-q:a", "2", str(original),
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Keep unusual dual-track imports usable if mixing fails.
            extract_audio(src, original, dual["vocal"])
        source = "mugen-dual"
        needs_separate = False
    elif src.suffix.lower() == ".mp3":
        # MP3 is already in the canonical audio format.  Keep the downloaded
        # file byte-for-byte and normalize its managed filename instead of
        # decoding/re-encoding or retaining a second mugen.mp3 copy.
        if src != original:
            src.replace(original)
        source = "mugen"
        needs_separate = True
    else:
        extract_audio(src, original)
        source = "mugen"
        needs_separate = True
    has_video = False
    if video:
        has_video = install_video(src, out_dir / "mtv.mp4")
    return {
        "file": "original.mp3" if original.exists() else "",
        "source": source,
        "dual_audio": bool(dual),
        "needs_separate": needs_separate,
        "has_video": has_video,
    }


def import_mugen_song(kid: str, out_dir: Path, query: str = "") -> dict[str, Any]:
    from lovktv.pipeline.lyrics import write_subtitles

    out_dir.mkdir(parents=True, exist_ok=True)
    kara = fetch_kara(kid)
    language = pick_language(kara) or "ja"
    title = pick_title(kara)
    artist = pick_artist(kara)
    lyrics_name = ""
    for info in kara.get("lyrics_infos") or []:
        if isinstance(info, dict) and info.get("filename"):
            lyrics_name = str(info["filename"])
            if info.get("default"):
                break
    if not lyrics_name:
        raise RuntimeError("这首没有 Karaoke Mugen 歌词")
    ass_path = out_dir / "mugen.ass"
    from lovktv.catalog.mugen_index import GITLAB_LYRICS

    quoted = urllib.parse.quote(lyrics_name)
    try:
        download_file(GITLAB_LYRICS.format(name=quoted), ass_path, timeout=30)
    except Exception:
        download_file_resilient(MUGEN_LYRICS.format(name=quoted), ass_path, timeout=20)
    timeline = timeline_from_ass(
        ass_path.read_text(encoding="utf-8", errors="replace"), language
    )
    write_subtitles(timeline, out_dir)
    (out_dir / "lyrics.lrc").write_text(
        lrc_from_cues(timeline["cues"]), encoding="utf-8"
    )

    media_name = str(kara.get("mediafile") or "")
    media_path = out_dir / f"mugen{Path(media_name).suffix.lower() or '.mp4'}"
    audio = {
        "file": "",
        "source": "mugen",
        "dual_audio": False,
        "needs_separate": True,
        "has_video": False,
    }
    if media_name:
        media_url = MUGEN_MEDIA.format(name=urllib.parse.quote(media_name))
        try:
            try:
                download_file(media_url, media_path, timeout=45, min_size=20_000)
            except Exception:
                download_file_resilient(
                    media_url, media_path, timeout=45, min_size=20_000
                )
            audio = prepare_media(media_path, out_dir)
        except Exception as exc:
            print(f"[lovktv] mugen media skipped: {exc}", flush=True)
    if audio.get("has_video"):
        timeline["native_video"] = True
        write_subtitles(timeline, out_dir)
    skeleton = {
        "title": f"{title} · {artist}".strip(" ·"),
        "artist": artist,
        "language": language,
        "source": {
            "provider": "karaoke-mugen",
            "kid": kid,
            "query": query,
            "songname": kara.get("songname") or title,
            "media": media_name,
            "lyrics": lyrics_name,
        },
        "audio": audio,
        "cover": "",
        "needs_separate": audio.get("needs_separate", True),
        "needs_align": False,
        "has_video": audio.get("has_video", False),
        "sentences": [
            {"id": f"s{index}", "timestamp_ms": cue["start_ms"], "raw": cue["text"]}
            for index, cue in enumerate(timeline["cues"], 1)
        ],
    }
    (out_dir / "skeleton.json").write_text(
        json.dumps(skeleton, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return skeleton


def attach_vocal_audio(out_dir: Path, skeleton: dict[str, Any]) -> bool:
    """If this kara is off-vocal, pull the matching vocal media as original.mp3."""
    source = skeleton.get("source") if isinstance(skeleton.get("source"), dict) else {}
    current = str(source.get("kid") or "")
    query = str(source.get("query") or skeleton.get("title") or "")
    if not query:
        return False
    # Keep using the exact sibling selected during the initial import when it
    # is recorded in the skeleton.  Re-searching by title can pick the
    # off-vocal entry again (Mugen has several near-duplicate versions), which
    # would silently replace the original track with another accompaniment
    # during a forced refresh.
    stored_kid = str(source.get("vocal_kid") or "")
    hit = None
    if stored_kid and stored_kid != current:
        kid = stored_kid
    else:
        # The local index treats a multi-word query as an AND expression, so
        # ``群青 YOASOBI`` can return nothing even though each term works on
        # its own. Retry with the title and retain the artist from the Mugen
        # songname to avoid selecting an unrelated “Gunjou” entry.
        songname = str(source.get("songname") or "")
        artist_hint = ""
        parts = [part.strip() for part in songname.split(" - ")]
        if len(parts) >= 2:
            artist_hint = parts[1].casefold()
        title_hint = query.split()[0] if query.split() else query
        for search_query in dict.fromkeys((query, title_hint)):
            hits = search_mugen(search_query, count=8).get("hits") or []
            if artist_hint:
                matching = [
                    item
                    for item in hits
                    if artist_hint in str(item.get("songname") or "").casefold()
                ]
                hit = pick_vocal_hit(matching or hits)
            else:
                hit = pick_vocal_hit(hits)
            if hit and not hit.get("off_vocal"):
                break
        kid = str((hit or {}).get("id") or "")
    if not kid or kid == current or (hit and hit.get("off_vocal")):
        return False
    kara = fetch_kara(kid)
    media_name = str(kara.get("mediafile") or "")
    if not media_name:
        return False
    tmp = out_dir / f"mugen-vocal{Path(media_name).suffix.lower() or '.mp4'}"
    try:
        download_file(
            MUGEN_MEDIA.format(name=urllib.parse.quote(media_name)),
            tmp,
            timeout=600,
            min_size=20_000,
        )
        extract_audio(tmp, out_dir / "original.mp3")
        extract_audio(tmp, out_dir / "guide.m4a")
    finally:
        tmp.unlink(missing_ok=True)
    if not (out_dir / "original.mp3").exists():
        return False
    source["vocal_kid"] = kid
    source["vocal_media"] = media_name
    skeleton["source"] = source
    audio = skeleton.get("audio") if isinstance(skeleton.get("audio"), dict) else {}
    audio["has_original_vocal"] = True
    skeleton["audio"] = audio
    (out_dir / "skeleton.json").write_text(
        json.dumps(skeleton, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True
