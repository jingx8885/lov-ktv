"""Local Karaoke Mugen catalog from the public GitLab karaokebase.

kara.moe (France) is often unreachable from the production host. Metadata
and lyrics live on GitLab, which is reachable. Search uses a compact index
built from karaokes/ + tags/; the live kara.moe API is only a fallback.
"""

from __future__ import annotations

import json
import os
import threading
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from lovktv.config import DATA_DIR

GITLAB_PROJECT = 32_123_952
GITLAB_ARCHIVE = (
    f"https://gitlab.com/api/v4/projects/{GITLAB_PROJECT}/repository/archive.zip"
    "?sha=master&path={path}"
)
GITLAB_KARA = (
    "https://gitlab.com/kara.moe/karaokebase/-/raw/master/karaokes/{kid}.kara.json"
)
GITLAB_LYRICS = "https://gitlab.com/kara.moe/karaokebase/-/raw/master/lyrics/{name}"
INDEX_TTL_SEC = 7 * 24 * 3600
LANG_FROM_TAG = {
    "jpn": "ja",
    "japanese": "ja",
    "ja": "ja",
    "eng": "en",
    "english": "en",
    "en": "en",
    "chi": "zh",
    "zho": "zh",
    "cmn": "zh",
    "yue": "zh",
    "chinese": "zh",
    "zh": "zh",
    "kor": "ko",
    "korean": "ko",
    "ko": "ko",
}

_lock = threading.Lock()
_items: list[dict[str, Any]] | None = None
_building = False
_ready = threading.Event()


def index_path(root: Path | None = None) -> Path:
    return (root or DATA_DIR) / "mugen" / "index.json"


def reset_for_tests() -> None:
    global _items, _building
    with _lock:
        _items = None
        _building = False
        _ready.set()
        _ready.clear()


def set_items_for_tests(items: list[dict[str, Any]] | None) -> None:
    global _items
    with _lock:
        _items = None if items is None else list(items)
        _ready.set()


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return folded.casefold()


def _tag_names(tag: dict[str, Any]) -> list[str]:
    i18n = tag.get("i18n") if isinstance(tag.get("i18n"), dict) else {}
    values = [
        tag.get("name"),
        *(i18n.values() if i18n else ()),
        *(tag.get("aliases") or []),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = str(value or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def parse_tag_file(raw: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    tag = raw.get("tag") if isinstance(raw.get("tag"), dict) else raw
    tid = str(tag.get("tid") or "").strip()
    if not tid:
        return None
    return tid, {
        "name": str(tag.get("name") or ""),
        "i18n": tag.get("i18n") if isinstance(tag.get("i18n"), dict) else {},
        "aliases": [str(item) for item in (tag.get("aliases") or []) if item],
    }


def _names_for(
    tag_ids: dict[str, Any], key: str, tags: dict[str, dict[str, Any]]
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tid in tag_ids.get(key) or []:
        tag = tags.get(str(tid)) or {}
        for name in _tag_names(tag):
            if name in seen:
                continue
            seen.add(name)
            out.append(name)
    return out


def _language(tag_ids: dict[str, Any], tags: dict[str, dict[str, Any]]) -> str:
    for name in _names_for(tag_ids, "langs", tags):
        mapped = LANG_FROM_TAG.get(name.lower())
        if mapped:
            return mapped
    return ""


def artist_from_songname(songname: str) -> str:
    parts = [part.strip() for part in (songname or "").split(" - ") if part.strip()]
    if len(parts) >= 3:
        return parts[1]
    return ""


def kara_to_item(
    raw: dict[str, Any], tags: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    from lovktv.catalog.mugen import is_off_vocal

    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    kid = str(data.get("kid") or "").strip()
    if not kid:
        return None
    titles = data.get("titles") if isinstance(data.get("titles"), dict) else {}
    songname = str(data.get("songname") or "")
    tag_ids = data.get("tags") if isinstance(data.get("tags"), dict) else {}
    tag_map = tags or {}
    artists = _names_for(tag_ids, "singergroups", tag_map) + _names_for(
        tag_ids, "singers", tag_map
    )
    if not artists:
        parsed = artist_from_songname(songname)
        if parsed:
            artists = [parsed]
    medias = raw.get("medias") if isinstance(raw.get("medias"), list) else []
    media = next(
        (item for item in medias if isinstance(item, dict) and item.get("default")),
        None,
    )
    if media is None:
        media = next((item for item in medias if isinstance(item, dict)), {})
    lyrics = ""
    for info in media.get("lyrics") or []:
        if isinstance(info, dict) and info.get("filename"):
            lyrics = str(info["filename"])
            if info.get("default"):
                break
    title_values = [str(value) for value in titles.values() if value]
    return {
        "kid": kid,
        "titles": {str(key): str(value) for key, value in titles.items() if value},
        "titles_default_language": str(data.get("titles_default_language") or ""),
        "songname": songname,
        "artists": artists,
        "series": _names_for(tag_ids, "series", tag_map),
        "language": _language(tag_ids, tag_map) or "ja",
        "duration": int(media.get("duration") or 0),
        "media": str(media.get("filename") or raw.get("mediafile") or ""),
        "lyrics": lyrics,
        "off_vocal": is_off_vocal(songname, *title_values),
    }


def item_to_kara(item: dict[str, Any]) -> dict[str, Any]:
    lyrics = str(item.get("lyrics") or "")
    return {
        "kid": item.get("kid") or "",
        "titles": item.get("titles") or {},
        "titles_default_language": item.get("titles_default_language") or "",
        "songname": item.get("songname") or "",
        "singers": [{"name": name} for name in item.get("artists") or []],
        "series": [{"name": name} for name in item.get("series") or []],
        "langs": [{"name": item.get("language") or "ja"}],
        "lyrics_infos": [{"filename": lyrics, "default": True}] if lyrics else [],
        "mediafile": item.get("media") or "",
        "duration": int(item.get("duration") or 0),
    }


def load_json_bytes(raw: bytes) -> dict[str, Any] | None:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_items_from_zip(
    kara_zip: Path, tag_zip: Path | None = None
) -> list[dict[str, Any]]:
    tags: dict[str, dict[str, Any]] = {}
    if tag_zip and tag_zip.exists():
        with zipfile.ZipFile(tag_zip) as archive:
            for name in archive.namelist():
                if not name.endswith(".tag.json"):
                    continue
                parsed = load_json_bytes(archive.read(name))
                if not parsed:
                    continue
                row = parse_tag_file(parsed)
                if row:
                    tags[row[0]] = row[1]
    items: list[dict[str, Any]] = []
    with zipfile.ZipFile(kara_zip) as archive:
        for name in archive.namelist():
            if not name.endswith(".kara.json"):
                continue
            parsed = load_json_bytes(archive.read(name))
            if not parsed:
                continue
            item = kara_to_item(parsed, tags)
            if item:
                items.append(item)
    return items


def build_items_from_files(
    kara_files: list[dict[str, Any]], tag_files: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    tags: dict[str, dict[str, Any]] = {}
    for raw in tag_files or []:
        row = parse_tag_file(raw)
        if row:
            tags[row[0]] = row[1]
    items: list[dict[str, Any]] = []
    for raw in kara_files:
        item = kara_to_item(raw, tags)
        if item:
            items.append(item)
    return items


def _score(item: dict[str, Any], needle: str) -> int | None:
    titles = [_norm(value) for value in (item.get("titles") or {}).values()]
    artists = [_norm(value) for value in item.get("artists") or []]
    series = [_norm(value) for value in item.get("series") or []]
    songname = _norm(str(item.get("songname") or ""))
    if any(title == needle for title in titles):
        return 0
    if any(title.startswith(needle) for title in titles if title):
        return 1
    if any(needle in title for title in titles):
        return 2
    if any(needle in artist for artist in artists):
        return 3
    if any(needle in name for name in series):
        return 4
    if needle in songname:
        return 5
    return None


def search_items(
    items: list[dict[str, Any]], query: str, count: int = 10, page: int = 1
) -> dict[str, Any]:
    page = max(1, int(page))
    count = max(1, min(int(count), 30))
    needle = _norm(query).strip()
    ranked: list[tuple[int, dict[str, Any]]] = []
    if needle:
        for item in items:
            score = _score(item, needle)
            if score is None:
                continue
            ranked.append((score, item))
        ranked.sort(
            key=lambda row: (
                row[0],
                bool(row[1].get("off_vocal")),
                str(
                    (row[1].get("titles") or {}).get("jpn")
                    or row[1].get("songname")
                    or ""
                ),
            )
        )
        matched = [item for _, item in ranked]
    else:
        matched = list(items)
    start = (page - 1) * count
    page_items = matched[start : start + count]
    return {
        "query": query,
        "page": page,
        "count": count,
        "has_more": start + len(page_items) < len(matched),
        "hits": page_items,
        "total": len(matched),
    }


def read_cache(root: Path | None = None) -> list[dict[str, Any]]:
    path = index_path(root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        items = payload
        built_at = path.stat().st_mtime
    elif isinstance(payload, dict):
        items = payload.get("items") or []
        built_at = float(payload.get("built_at") or path.stat().st_mtime)
    else:
        return []
    if not isinstance(items, list) or not items:
        return []
    if time.time() - built_at > INDEX_TTL_SEC:
        return []
    return [item for item in items if isinstance(item, dict) and item.get("kid")]


def write_cache(items: list[dict[str, Any]], root: Path | None = None) -> Path:
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.part")
    tmp.write_text(
        json.dumps(
            {"built_at": time.time(), "count": len(items), "items": items},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def cached_items(root: Path | None = None) -> list[dict[str, Any]]:
    global _items
    if _items:
        return _items
    items = read_cache(root)
    if items:
        with _lock:
            _items = items
    return items


def _allow_download() -> bool:
    if (
        os.environ.get("PYTEST_CURRENT_TEST")
        and os.environ.get("LOVKTV_MUGEN_INDEX_DOWNLOAD") != "1"
    ):
        return False
    return os.environ.get("LOVKTV_MUGEN_INDEX_DOWNLOAD", "1") != "0"


def _download_archives(root: Path) -> list[dict[str, Any]]:
    from lovktv.catalog.mugen import download_file

    work = root / "mugen" / "build"
    work.mkdir(parents=True, exist_ok=True)
    kara_zip = work / "karaokes.zip"
    tag_zip = work / "tags.zip"
    download_file(
        GITLAB_ARCHIVE.format(path="karaokes"), kara_zip, timeout=90, min_size=1_000_000
    )
    try:
        download_file(
            GITLAB_ARCHIVE.format(path="tags"), tag_zip, timeout=90, min_size=100_000
        )
    except Exception:
        tag_zip = Path()
    try:
        return build_items_from_zip(kara_zip, tag_zip if tag_zip.exists() else None)
    finally:
        kara_zip.unlink(missing_ok=True)
        if tag_zip:
            tag_zip.unlink(missing_ok=True)


def _build(root: Path) -> list[dict[str, Any]]:
    items = _download_archives(root)
    if items:
        write_cache(items, root)
    return items


def ensure_index(root: Path | None = None, wait: float = 0) -> list[dict[str, Any]]:
    global _items, _building
    dest = root or DATA_DIR
    items = cached_items(dest)
    if items:
        return items
    with _lock:
        items = _items or read_cache(dest)
        if items:
            _items = items
            return items
        if not _building and _allow_download():
            _building = True
            _ready.clear()

            def worker() -> None:
                global _items, _building
                try:
                    built = _build(dest)
                    with _lock:
                        _items = built
                    print(f"[lovktv] mugen index ready {len(built)}", flush=True)
                except Exception as exc:
                    print(f"[lovktv] mugen index failed: {exc}", flush=True)
                finally:
                    with _lock:
                        _building = False
                    _ready.set()

            threading.Thread(target=worker, name="mugen-index", daemon=True).start()
    if wait > 0 and _building:
        _ready.wait(wait)
        return cached_items(dest)
    return _items or read_cache(dest) or []


def prefetch_index() -> None:
    ensure_index(wait=0)


def find_item(kid: str, root: Path | None = None) -> dict[str, Any] | None:
    kid = str(kid or "").strip()
    if not kid:
        return None
    for item in cached_items(root):
        if item.get("kid") == kid:
            return item
    return None


def fetch_kara_json(kid: str) -> dict[str, Any]:
    from lovktv.catalog.mugen import get_json

    return get_json(GITLAB_KARA.format(kid=kid), timeout=20)
