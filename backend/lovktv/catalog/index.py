"""Local library search, A-Z index, and pagination."""

from __future__ import annotations

import math
import unicodedata
from collections import Counter
from typing import Any

PAGE_SIZE = 12
LETTERS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ#")
_LETTER_RANK = {letter: index for index, letter in enumerate(LETTERS)}

_GBK_INITIALS = (
    (0xB0A1, "A"),
    (0xB0C5, "B"),
    (0xB2C1, "C"),
    (0xB4EE, "D"),
    (0xB6EA, "E"),
    (0xB7A2, "F"),
    (0xB8C1, "G"),
    (0xB9FE, "H"),
    (0xBBF7, "J"),
    (0xBFA6, "K"),
    (0xC0AC, "L"),
    (0xC2E8, "M"),
    (0xC4C3, "N"),
    (0xC5B6, "O"),
    (0xC5BE, "P"),
    (0xC6DA, "Q"),
    (0xC8BB, "R"),
    (0xC8F6, "S"),
    (0xCBFA, "T"),
    (0xCDDA, "W"),
    (0xCEF4, "X"),
    (0xD1B9, "Y"),
    (0xD4D1, "Z"),
)

_KANA_ROWS = (
    ("あいうえおアイウエオぁぃぅぇぉァィゥェォ", "A"),
    ("かきくけこカキクケコがぎぐげごガギグゲゴ", "K"),
    ("さしすせそサシスセソざじずぜぞザジズゼゾ", "S"),
    ("たちつてとタチツテトだぢづでどダヂヅデドっッ", "T"),
    ("なにぬねのナニヌネノ", "N"),
    ("はひふへほハヒフヘホばびぶべぼバビブベボぱぴぷぺぽパピプペポ", "H"),
    ("まみむめもマミムメモ", "M"),
    ("やゆよヤユヨゃゅょャュョ", "Y"),
    ("らりるれろラリルレロ", "R"),
    ("わをんワヲンゎヮ", "W"),
)

_KAKASI_CONVERTER = None


def display_title(song: dict[str, Any]) -> str:
    title = str(song.get("title") or "").strip()
    if " · " in title:
        return title.split(" · ", 1)[0].strip()
    return title


def display_artist(song: dict[str, Any]) -> str:
    artist = str(song.get("artist") or "").strip()
    if artist:
        return artist
    title = str(song.get("title") or "")
    if " · " in title:
        return title.split(" · ", 1)[1].strip()
    return ""


def _han_initial(char: str) -> str:
    try:
        raw = char.encode("gbk")
    except UnicodeEncodeError:
        return "#"
    if len(raw) != 2:
        return "#"
    code = raw[0] * 256 + raw[1]
    if code < 0xB0A1 or code > 0xD7F9:
        return "#"
    previous = "#"
    for edge, letter in _GBK_INITIALS:
        if code < edge:
            return previous
        previous = letter
    return previous


def _kana_initial(char: str) -> str:
    for row, letter in _KANA_ROWS:
        if char in row:
            return letter
    return "#"


def _japanese_initial(text: str) -> str:
    """Return the Hepburn/Romaji initial for a Japanese title or artist."""
    global _KAKASI_CONVERTER
    try:
        if _KAKASI_CONVERTER is None:
            from pykakasi import kakasi

            _KAKASI_CONVERTER = kakasi()
        converted = _KAKASI_CONVERTER.convert(unicodedata.normalize("NFKC", text or ""))
    except Exception:
        return "#"
    for part in converted:
        reading = str(part.get("hepburn") or "")
        for char in reading:
            if char.isascii() and char.isalpha():
                return char.upper()
            if char.isascii() and char.isdigit():
                return "#"
    return "#"


def first_letter(text: str, language: str = "") -> str:
    if str(language or "").strip().lower() in {"ja", "jpn", "japanese"}:
        return _japanese_initial(text)
    folded = unicodedata.normalize("NFKC", text or "")
    for char in folded:
        if char.isascii() and char.isalpha():
            return char.upper()
        if char.isascii() and char.isdigit():
            return "#"
        if "\u4e00" <= char <= "\u9fff":
            return _han_initial(char)
        if "\u3040" <= char <= "\u30ff":
            return _kana_initial(char)
    return "#"


def song_letter(song: dict[str, Any], by: str = "title") -> str:
    text = (
        (display_artist(song) or display_title(song))
        if by == "artist"
        else display_title(song)
    )
    language = str(song.get("language") or "").strip().lower()
    source = str(song.get("audio_source") or "").strip().lower()
    # Japanese kanji has no reliable Unicode/pinyin ordering.  Use the
    # language/source metadata (and kana as a safe fallback) to read it in
    # Hepburn. Karaoke Mugen's catalog is Japanese even for kanji-only titles.
    if (
        language in {"ja", "jpn", "japanese"}
        or source.startswith("mugen")
        or any("\u3040" <= char <= "\u30ff" for char in text)
    ):
        return _japanese_initial(text)
    return first_letter(text)


def library_sort_key(song: dict[str, Any], by: str = "title") -> tuple[int, str, str, str]:
    """Return the stable A-Z ordering key used by every library response.

    ``#`` represents titles (or artists) that do not start with a Latin,
    Han, or kana character.  It is intentionally ranked after ``Z`` instead
    of relying on Python's punctuation ordering.
    """
    letter = song_letter(song, by)
    return (
        _LETTER_RANK.get(letter, _LETTER_RANK["#"]),
        display_title(song).casefold(),
        display_artist(song).casefold(),
        str(song.get("id") or ""),
    )


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").casefold()


def song_matches(song: dict[str, Any], query: str, by: str = "all") -> bool:
    needle = _norm(query).strip()
    if not needle:
        return True
    title = _norm(display_title(song))
    artist = _norm(display_artist(song))
    full = _norm(str(song.get("title") or ""))
    if by == "title":
        return needle in title
    if by == "artist":
        return needle in artist
    return needle in title or needle in artist or needle in full


def prefer_native_library(songs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide composed-MTV copies once the same title has an official MV."""
    native_keys = {
        display_title(song).casefold()
        for song in songs
        if song.get("native_video")
        or str(song.get("audio_source") or "").startswith("mugen")
    }
    return [
        song
        for song in songs
        if song.get("native_video")
        or str(song.get("audio_source") or "").startswith("mugen")
        or display_title(song).casefold() not in native_keys
    ]


def query_library(
    songs: list[dict[str, Any]],
    q: str = "",
    by: str = "all",
    letter: str = "",
    page: int = 1,
    count: int = PAGE_SIZE,
    after: str = "",
) -> dict[str, Any]:
    by = by if by in {"all", "title", "artist"} else "all"
    key = letter.strip().upper()
    if key in {"", "ALL", "*"}:
        key = ""
    if key and key not in LETTERS:
        key = "#"
    count = min(50, max(1, int(count) or PAGE_SIZE))
    index_by = "artist" if by == "artist" else "title"
    matched = [song for song in songs if song_matches(song, q, by)]
    indexed = [{**song, "letter": song_letter(song, index_by)} for song in matched]
    counts = Counter(item["letter"] for item in indexed)
    if key:
        indexed = [item for item in indexed if item["letter"] == key]
    indexed.sort(key=lambda item: library_sort_key(item, index_by))
    total = len(indexed)
    pages = max(1, math.ceil(total / count)) if total else 1
    after_id = str(after or "").strip()
    start = None
    if after_id:
        for index, item in enumerate(indexed):
            if str(item.get("id") or "") == after_id:
                start = index + 1
                break
    if start is None:
        page = min(max(1, int(page) or 1), pages)
        start = (page - 1) * count
    else:
        page = min(pages, start // count + 1) if total else 1
    return {
        "songs": indexed[start : start + count],
        "total": total,
        "lib_total": len(songs),
        "page": page,
        "pages": pages,
        "count": count,
        "q": q,
        "by": by,
        "letter": key,
        "after": after_id,
        "letters": [
            {"key": item, "count": counts[item]} for item in LETTERS if counts[item]
        ],
    }
