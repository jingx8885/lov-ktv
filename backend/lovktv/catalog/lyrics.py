"""Lyrics retrieval and LRC parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from .search import TONZHON_API, post_form

LRC_LINE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
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


def parse_lrc(lrc: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lrc.splitlines():
        textline = line.strip()
        match = LRC_LINE.match(textline)
        if not match:
            continue
        mins, secs, text = match.group(1), match.group(2), match.group(3).strip()
        ms = int((int(mins) * 60 + float(secs)) * 1000)
        if not text or text in {"-", "—", "–"}:
            if not text:
                for item in reversed(out):
                    if item.get("end_ms") is None and item["ms"] < ms:
                        item["end_ms"] = ms
                        break
            continue
        if any(text.startswith(prefix) for prefix in META_PREFIX):
            continue
        if re.match(r"^(作词|作曲|编曲|作詞|編曲)\s*[:：]", text):
            continue
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
