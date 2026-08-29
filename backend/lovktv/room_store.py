"""SQLite-backed persistence adapter for karaoke rooms.

This module is intentionally boring: room semantics stay in ``RoomService``
while SQL/store access lives behind one replaceable adapter.  The adapter
currently delegates to the legacy store module during the incremental split;
the next R4 step can move the SQL implementation here without touching the
HTTP/WebSocket layers.
"""

from __future__ import annotations

from typing import Any, Protocol

from lovktv import store


class RoomRepository(Protocol):
    """Persistence contract consumed by the room domain service."""

    def room_snapshot(self, code: str) -> dict[str, Any]: ...

    def enqueue(self, code: str, song_id: str) -> dict[str, Any]: ...

    def bump(self, code: str, item_id: str) -> dict[str, Any]: ...

    def skip(self, code: str) -> dict[str, Any]: ...

    def play_now(self, code: str, item_id: str = "", song_id: str = "") -> dict[str, Any]: ...

    def set_mix(
        self,
        code: str,
        vocal_mix: float | None = None,
        volume: int | None = None,
        mic_gain: int | None = None,
        lyric_mode: str | None = None,
        paused: bool | None = None,
    ) -> dict[str, Any]: ...

    def set_room_lan(
        self,
        code: str,
        origin: str,
        mic_port: int | None = None,
        mic_sample_rate: int | None = None,
    ) -> dict[str, Any]: ...


class SqliteRoomStore:
    """Persistence implementation used by the default room service."""

    def room_snapshot(self, code: str) -> dict[str, Any]:
        return store.room_snapshot(code)

    def enqueue(self, code: str, song_id: str) -> dict[str, Any]:
        return store.enqueue(code, song_id)

    def bump(self, code: str, item_id: str) -> dict[str, Any]:
        return store.bump(code, item_id)

    def skip(self, code: str) -> dict[str, Any]:
        return store.skip(code)

    def play_now(self, code: str, item_id: str = "", song_id: str = "") -> dict[str, Any]:
        return store.play_now(code, item_id, song_id)

    def set_mix(
        self,
        code: str,
        vocal_mix: float | None = None,
        volume: int | None = None,
        mic_gain: int | None = None,
        lyric_mode: str | None = None,
        paused: bool | None = None,
    ) -> dict[str, Any]:
        return store.set_mix(code, vocal_mix, volume, mic_gain, lyric_mode, paused)

    def set_room_lan(
        self,
        code: str,
        origin: str,
        mic_port: int | None = None,
        mic_sample_rate: int | None = None,
    ) -> dict[str, Any]:
        """Persist LAN host metadata when the host feature is available.

        The method is optional during the rolling migration: older store
        modules simply do not expose it, in which case callers get a clear
        capability error instead of an obscure attribute failure.
        """
        setter = getattr(store, "set_room_lan", None)
        if setter is None:
            raise NotImplementedError("当前存储实现不支持局域网房间")
        return setter(code, origin, mic_port, mic_sample_rate)
