"""Lyrics retrieval and LRC parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from .search import TONZHON_API, post_form

LRC_TAG = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
LRC_WORD_TAG = re.compile(r"<\d+:\d+(?:\.\d+)?>")
EMPTY_MARKERS = {"-", "—", "–"}
META_PREFIX = (
    "作词",
    "作曲",
    "编曲",
    "作詞",
    "編曲",
    "制作人",
    "製作人",
    "制作",
    "Lyrics",
    "lyrics by",
    "composer",
    "arranger",
    "Producer",
    "producer",
)


def fetch_lyric(song_id: str, source: str = "netease") -> str:
    raw = post_form(TONZHON_API, {"types": "lyric", "id": song_id, "source": source})
    obj = json.loads(raw.decode("utf-8"))
    return str(obj.get("lyric") or "")


def _stamp_ms(mins: str, secs: str) -> int:
    return int((int(mins) * 60 + float(secs)) * 1000)


def _leading_stamps(text: str) -> tuple[list[int], str]:
    """Pull every leading [mm:ss.xx] tag. Chorus repeats share one lyric line."""
    stamps: list[int] = []
    pos = 0
    length = len(text)
    while pos < length:
        while pos < length and text[pos].isspace():
            pos += 1
        match = LRC_TAG.match(text, pos)
        if not match:
            break
        stamps.append(_stamp_ms(match.group(1), match.group(2)))
        pos = match.end()
    return stamps, text[pos:].strip()


def _lyric_body(text: str) -> str:
    body = LRC_WORD_TAG.sub("", text)
    _, rest = _leading_stamps(body)
    return re.sub(r"\s+", " ", rest).strip()


def _is_meta_lyric(text: str) -> bool:
    if any(text.startswith(prefix) for prefix in META_PREFIX):
        return True
    return bool(re.match(r"^(作词|作曲|编曲|作詞|編曲)\s*[:：]", text))


def parse_lrc(lrc: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lrc.splitlines():
        stamps, raw_text = _leading_stamps(line.strip())
        if not stamps:
            continue
        text = _lyric_body(raw_text)
        if not text or text in EMPTY_MARKERS:
            if not text:
                ms = stamps[0]
                for item in reversed(out):
                    if item.get("end_ms") is None and item["ms"] < ms:
                        item["end_ms"] = ms
                        break
            continue
        if _is_meta_lyric(text):
            continue
        for ms in stamps:
            out.append({"ms": ms, "text": text})
    out.sort(key=lambda item: item["ms"])
    dedup: list[dict[str, Any]] = []
    for item in out:
        if item.get("end_ms") is not None and int(item["end_ms"]) <= item["ms"]:
            item = dict(item)
            item.pop("end_ms", None)
        if (
            dedup
            and dedup[-1]["text"] == item["text"]
            and item["ms"] - dedup[-1]["ms"] < 300
        ):
            continue
        dedup.append(item)
    return dedup
