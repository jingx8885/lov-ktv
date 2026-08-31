"""Stable application contracts shared by transports and adapters."""

from __future__ import annotations

from typing import Literal, TypedDict

RoomAction = Literal["enqueue", "bump", "skip", "play", "mix"]


class QueueItem(TypedDict, total=False):
    id: str
    song_id: str
    position: int
    title: str
    artist: str
    status: str
    language: str


class RoomSnapshot(TypedDict, total=False):
    code: str
    created_at: int
    queue: list[QueueItem]
    now_index: int
    now_playing: QueueItem | None
    vocal_mix: float
    volume: int
    mic_gain: int
    lyric_mode: str
    display_mode: str
    paused: int
    mic_on: bool
    mic_peer: str
    lan_origin: str
    lan_mic_port: int
    lan_mic_sample_rate: int
    lan_seen_at: int
