"""Application-level room commands.

The HTTP and WebSocket transports both use this module for room mutations.
Keeping the command dispatch here prevents the two transports (and the TV
fallback, which mirrors the same contract) from slowly acquiring different
room semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from lovktv.domain.contracts import RoomAction, RoomSnapshot
from lovktv.domain.room_contract import normalize_command, normalize_room_code
from lovktv.storage.room_store import RoomRepository, SqliteRoomStore


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
    display_mode: str | None = None
    paused: bool | None = None

    @classmethod
    def from_payload(
        cls, action: str, payload: Mapping[str, Any] | None = None
    ) -> "RoomCommand":
        """Build a command from either REST or WebSocket JSON.

        Unknown actions are rejected before touching the store.  The payload
        values are intentionally left in their existing scalar form; the
        store remains the single place that clamps room values.
        """

        normalized = normalize_command(action, payload)
        name = normalized["action"]
        data = normalized

        return cls(
            action=name,  # type: ignore[arg-type]
            song_id=str(data.get("song_id") or ""),
            item_id=str(data.get("id") or data.get("item_id") or ""),
            vocal_mix=data.get("vocal_mix"),
            volume=data.get("volume"),
            mic_gain=data.get("mic_gain"),
            lyric_mode=str(data["lyric_mode"])
            if data.get("lyric_mode") is not None
            else None,
            display_mode=str(data["display_mode"])
            if data.get("display_mode") is not None
            else None,
            paused=data.get("paused"),
        )


class RoomService:
    """Execute room mutations independently of HTTP/WebSocket transport."""

    def __init__(self, repository: RoomRepository | None = None) -> None:
        self.repository = repository or SqliteRoomStore()

    def snapshot(self, code: str) -> RoomSnapshot:
        return self.repository.room_snapshot(str(code or "").upper())

    def execute(self, code: str, command: RoomCommand) -> dict[str, Any]:
        room = normalize_room_code(code)
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
                display_mode=command.display_mode,
                paused=command.paused,
            )
        # The dataclass type narrows this, but keep a defensive error for
        # callers that construct it dynamically.
        raise ValueError(f"未知房间命令：{command.action}")


room_service = RoomService()
