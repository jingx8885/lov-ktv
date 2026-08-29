"""Small request models shared by the room HTTP endpoints.

These models intentionally cover only transport validation.  Domain rules
(ready songs, queue ordering, clamping) remain in :mod:`room_service` and
``store`` so WebSocket and local-host callers get the same behavior.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RoomCommandPayload(BaseModel):
    id: str | None = None
    item_id: str | None = None
    song_id: str | None = None
    vocal_mix: float | None = None
    volume: int | None = None
    mic_gain: int | None = None
    lyric_mode: str | None = None
    paused: bool | int | float | str | None = None

    class Config:
        extra = "ignore"

    def as_dict(self) -> dict[str, Any]:
        # ``model_dump`` is pydantic v2; ``dict`` keeps this usable with the
        # pydantic v1 runtime used by older FastAPI installations.
        dump = getattr(self, "model_dump", None)
        if dump is not None:
            return dump(exclude_none=True)
        return self.dict(exclude_none=True)

