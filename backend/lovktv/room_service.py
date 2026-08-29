"""Application-level room commands.

The HTTP and WebSocket transports both use this module for room mutations.
Keeping the command dispatch here prevents the two transports (and the TV
fallback, which mirrors the same contract) from slowly acquiring different
room semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from lovktv.contracts import RoomAction, RoomSnapshot
from lovktv.room_store import RoomRepository, SqliteRoomStore


@dataclass(frozen=True)
class RoomCommand:
    """Transport-neutral representation of a room mutation."""

    action: RoomAction
    song_id: str = ""
    item_id: str = ""
    vocal_mix: float | None = None
    volume: int | None = None
    mic_gain: int | None = None
    lyric_mode: str | None = None
    paused: bool | None = None

    @classmethod
    def from_payload(cls, action: str, payload: Mapping[str, Any] | None = None) -> "RoomCommand":
        """Build a command from either REST or WebSocket JSON.

        Unknown actions are rejected before touching the store.  The payload
        values are intentionally left in their existing scalar form; the
        store remains the single place that clamps room values.
        """

        name = str(action or "").strip().lower()
        if name not in {"enqueue", "bump", "skip", "play", "mix"}:
            raise ValueError(f"未知房间命令：{name or '空'}")
        data = dict(payload or {})

        def optional_bool(key: str) -> bool | None:
            if key not in data or data[key] is None:
                return None
            raw = data[key]
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, (int, float)):
                return bool(raw)
            text = str(raw).strip().lower()
            return text in {"1", "true", "yes", "on"}

        return cls(
            action=name,  # type: ignore[arg-type]
            song_id=str(data.get("song_id") or ""),
            item_id=str(data.get("id") or data.get("item_id") or ""),
            vocal_mix=data.get("vocal_mix"),
            volume=data.get("volume"),
            mic_gain=data.get("mic_gain"),
            lyric_mode=str(data["lyric_mode"]) if data.get("lyric_mode") is not None else None,
            paused=optional_bool("paused"),
        )


class RoomService:
    """Execute room mutations independently of HTTP/WebSocket transport."""

    def __init__(self, repository: RoomRepository | None = None) -> None:
        self.repository = repository or SqliteRoomStore()

    def snapshot(self, code: str) -> RoomSnapshot:
        return self.repository.room_snapshot(str(code or "").upper())

    def execute(self, code: str, command: RoomCommand) -> dict[str, Any]:
        room = str(code or "").upper()
        if command.action == "enqueue":
            return self.repository.enqueue(room, command.song_id)
        if command.action == "bump":
            return self.repository.bump(room, command.item_id)
        if command.action == "skip":
            return self.repository.skip(room)
        if command.action == "play":
            return self.repository.play_now(room, command.item_id, command.song_id)
        if command.action == "mix":
            return self.repository.set_mix(
                room,
                vocal_mix=command.vocal_mix,
                volume=command.volume,
                mic_gain=command.mic_gain,
                lyric_mode=command.lyric_mode,
                paused=command.paused,
            )
        # The dataclass type narrows this, but keep a defensive error for
        # callers that construct it dynamically.
        raise ValueError(f"未知房间命令：{command.action}")


room_service = RoomService()
