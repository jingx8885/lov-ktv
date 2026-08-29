"""Runtime normalization for the room wire protocol."""

from __future__ import annotations

from typing import Any, Mapping


def normalize_room_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    if (
        not code
        or len(code) > 32
        or any(not (char.isalnum() or char in "-_") for char in code)
    ):
        raise ValueError("房间号无效")
    return code


def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_command(
    action: Any, payload: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    name = str(action or "").strip().lower()
    if name not in {"enqueue", "bump", "skip", "play", "mix"}:
        raise ValueError(f"未知房间命令：{name or '空'}")
    data = dict(payload or {})
    result: dict[str, Any] = {"action": name}
    for key in ("song_id", "id", "item_id"):
        if data.get(key) is not None:
            result[key] = str(data[key])
    for key in ("vocal_mix", "volume", "mic_gain", "lyric_mode"):
        if data.get(key) is not None:
            result[key] = data[key]
    if "paused" in data:
        result["paused"] = optional_bool(data.get("paused"))
    return result


def normalize_playback_event(
    action: Any, payload: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Normalize playback-only WS events before they reach the room service."""
    name = str(action or "").strip().lower()
    if name not in {"play", "skip", "bump"}:
        raise ValueError("播放控制事件无效")
    data = normalize_command(name, payload)
    if name in {"play", "bump"} and not (
        data.get("id") or data.get("item_id") or data.get("song_id")
    ):
        raise ValueError("播放控制事件缺少目标")
    return data
