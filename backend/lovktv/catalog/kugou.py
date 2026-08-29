"""Kugou word-level lyrics (KRC) as a supplement to NetEase LRC."""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
import zlib
from typing import Any

from lovktv.pipeline.language import detect_language
from lovktv.pipeline.lyrics import is_credit_lyric

KUGOU_SEARCH = "https://lyrics.kugou.com/search"
KUGOU_DOWNLOAD = "https://lyrics.kugou.com/download"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
KRC_KEY = bytes([64, 71, 97, 119, 94, 50, 116, 71, 81, 54, 49, 45, 206, 210, 110, 105])
KRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
KRC_WORD = re.compile(r"<(\d+),(\d+),\d+>([^<]*)")
KRC_META = re.compile(r"^\[(id|ar|ti|by|hash|al|sign|qq|total|offset|language):", re.I)
CREDIT_PREFIX = ("作词", "作曲", "编曲", "作詞", "編曲", "制作人", "製作人", "制作")


def _get_json(url: str, timeout: float = 15) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": BROWSER_UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def decode_krc(content: str) -> str:
    raw = base64.b64decode(content)
    if len(raw) <= 4:
        raise ValueError("KRC 太短")
    decrypted = bytes(
        byte ^ KRC_KEY[index % len(KRC_KEY)] for index, byte in enumerate(raw[4:])
    )
    plain = zlib.decompress(decrypted)
    if plain.startswith(b"\xef\xbb\xbf"):
        plain = plain[3:]
    return plain.decode("utf-8")


def _is_banner(text: str, title: str = "", artist: str = "") -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if any(compact.startswith(prefix) for prefix in CREDIT_PREFIX):
        return True
    if is_credit_lyric(text):
        return True
    if title:
        title_c = re.sub(r"\s+", "", title)
        artist_c = re.sub(r"\s+", "", artist)
        if compact in {title_c, f"{artist_c}-{title_c}", f"{title_c}-{artist_c}"}:
            return True
    return False


def parse_krc(raw: str, title: str = "", artist: str = "") -> list[dict[str, Any]]:
    offset = 0
    cues: list[dict[str, Any]] = []
    for line in (raw or "").replace("\r", "").splitlines():
        meta = KRC_META.match(line)
        if meta:
            if meta.group(1).lower() == "offset":
                try:
                    offset = int(line.split(":", 1)[1].rstrip("]"))
                except ValueError:
                    offset = 0
            continue
        match = KRC_LINE.match(line)
        if not match:
            continue
        start_ms = int(match.group(1)) + offset
        duration_ms = int(match.group(2))
        tokens: list[dict[str, Any]] = []
        for word_off, word_dur, word in KRC_WORD.findall(match.group(3)):
            text = word
            if not text:
                continue
            tok_start = start_ms + int(word_off)
            tok_end = tok_start + max(40, int(word_dur))
            if int(word_dur) <= 0 and tokens:
                tokens[-1]["text"] += text
                continue
            tokens.append(
                {"text": text, "start_ms": tok_start, "end_ms": tok_end, "reading": ""}
            )
        line_text = "".join(str(token["text"]) for token in tokens).strip()
        if not line_text or _is_banner(line_text, title, artist):
            continue
        end_ms = start_ms + max(duration_ms, 200)
        if tokens:
            start_ms = tokens[0]["start_ms"]
            end_ms = max(end_ms, tokens[-1]["end_ms"])
        cues.append(
            {
                "text": line_text,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "tokens": tokens,
            }
        )
    return cues


def timeline_from_krc(
    raw: str, title: str = "", artist: str = "", language: str | None = None
) -> dict[str, Any]:
    cues = parse_krc(raw, title=title, artist=artist)
    if not cues:
        raise RuntimeError("酷狗歌词是空的")
    lang = detect_language(
        "".join(str(cue.get("text") or "") for cue in cues), language
    )
    if lang == "en":
        from lovktv.pipeline.lyrics import merge_english_token_chunks

        for cue in cues:
            cue["tokens"] = merge_english_token_chunks(cue.get("tokens") or [])
    return {
        "language": lang,
        "alignment": "kugou",
        "alignment_source": "kugou-krc",
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


def search_kugou_lyrics(keyword: str, duration_ms: int = 0) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "ver": "1",
            "man": "yes",
            "client": "pc",
            "keyword": keyword,
            "duration": max(0, int(duration_ms or 0)),
            "hash": "",
        }
    )
    data = _get_json(f"{KUGOU_SEARCH}?{params}")
    if int(data.get("status") or 0) != 200:
        return []
    hits = []
    for item in data.get("candidates") or []:
        if isinstance(item, dict) and item.get("id") and item.get("accesskey"):
            hits.append(item)
    return hits


def download_kugou_krc(candidate: dict[str, Any]) -> str:
    params = urllib.parse.urlencode(
        {
            "ver": "1",
            "client": "pc",
            "id": candidate["id"],
            "accesskey": candidate["accesskey"],
            "fmt": "krc",
            "charset": "utf8",
        }
    )
    data = _get_json(f"{KUGOU_DOWNLOAD}?{params}")
    content = str(data.get("content") or "")
    if int(data.get("status") or 0) != 200 or not content:
        raise RuntimeError("酷狗歌词下载失败")
    return decode_krc(content)


def pick_candidate(
    candidates: list[dict[str, Any]],
    title: str = "",
    artist: str = "",
    duration_ms: int = 0,
) -> dict[str, Any] | None:
    ranked: list[tuple[int, dict[str, Any]]] = []
    title_c = re.sub(r"\s+", "", title or "")
    artist_c = re.sub(r"\s+", "", artist or "")
    for item in candidates:
        score = int(item.get("score") or 0)
        source = str(item.get("product_from") or "")
        song = re.sub(r"\s+", "", str(item.get("song") or ""))
        singer = re.sub(r"\s+", "", str(item.get("singer") or ""))
        if "官方" in source:
            score += 25
        if title_c and title_c in song:
            score += 10
        if artist_c and artist_c in singer:
            score += 10
        if duration_ms and item.get("duration"):
            if abs(int(item["duration"]) - duration_ms) <= 4000:
                score += 8
        ranked.append((score, item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1] if ranked else None


def fetch_kugou_lyrics(
    title: str,
    artist: str = "",
    duration_ms: int = 0,
    language: str | None = None,
) -> dict[str, Any] | None:
    """Search + download KRC. None if Kugou has nothing usable."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return None
    keyword = f"{artist} - {title}" if artist else title
    try:
        candidates = search_kugou_lyrics(keyword, duration_ms=duration_ms)
        if not candidates and artist:
            candidates = search_kugou_lyrics(title, duration_ms=duration_ms)
        chosen = pick_candidate(
            candidates, title=title, artist=artist, duration_ms=duration_ms
        )
        if not chosen:
            return None
        raw = download_kugou_krc(chosen)
        timeline = timeline_from_krc(raw, title=title, artist=artist, language=language)
    except Exception:
        return None
    return {
        "timeline": timeline,
        "lrc": lrc_from_cues(timeline["cues"]),
        "candidate": {
            "id": str(chosen.get("id") or ""),
            "song": str(chosen.get("song") or title),
            "singer": str(chosen.get("singer") or artist),
            "source": str(chosen.get("product_from") or "kugou"),
        },
    }
