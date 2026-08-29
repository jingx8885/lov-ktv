"""Runtime guards for persisted lyric timelines."""
from __future__ import annotations

from typing import Any


def normalize_timeline(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("cues"), list):
        raise ValueError("歌词时间轴无效")
    cues: list[dict[str, Any]] = []
    for raw in payload["cues"]:
        if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
            continue
        start = max(0, int(raw.get("start_ms") or 0))
        end = max(start + 1, int(raw.get("end_ms") or 0))
        cue = dict(raw)
        cue.update(text=str(raw["text"]).strip(), start_ms=start, end_ms=end)
        tokens: list[dict[str, Any]] = []
        for token in raw.get("tokens") or []:
            if not isinstance(token, dict) or not str(token.get("text") or ""):
                continue
            token_data = dict(token)
            token_data["start_ms"] = max(start, int(token.get("start_ms") or start))
            token_data["end_ms"] = max(token_data["start_ms"], min(end, int(token.get("end_ms") or end)))
            tokens.append(token_data)
        cue["tokens"] = tokens
        cues.append(cue)
    if not cues:
        raise ValueError("歌词时间轴无效")
    cues.sort(key=lambda cue: (cue["start_ms"], cue["end_ms"]))
    return {**payload, "cues": cues}
