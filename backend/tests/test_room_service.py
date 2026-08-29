import pytest

from lovktv.room_service import RoomCommand, room_service
from lovktv.room_service import RoomService


def test_command_parsing_normalizes_transport_payload():
    command = RoomCommand.from_payload(
        "mix",
        {
            "vocal_mix": 0.25,
            "volume": 120,
            "mic_gain": 40,
            "lyric_mode": "JA",
            "paused": 0,
        },
    )

    assert command.action == "mix"
    assert command.vocal_mix == 0.25
    assert command.volume == 120
    assert command.mic_gain == 40
    assert command.lyric_mode == "JA"
    assert command.paused is False


def test_command_parsing_rejects_unknown_action():
    with pytest.raises(ValueError, match="未知房间命令"):
        RoomCommand.from_payload("delete", {})


def test_service_can_use_repository_without_sqlite():
    calls = []

    class FakeRepository:
        def room_snapshot(self, code):
            calls.append(("snapshot", code))
            return {"code": code}

        def enqueue(self, code, song_id):
            calls.append(("enqueue", code, song_id))
            return {"code": code, "song_id": song_id}

        def bump(self, code, item_id):
            calls.append(("bump", code, item_id))
            return {"code": code}

        def skip(self, code):
            calls.append(("skip", code))
            return {"code": code}

        def play_now(self, code, item_id="", song_id=""):
            calls.append(("play", code, item_id, song_id))
            return {"code": code}

        def set_mix(self, code, **kwargs):
            calls.append(("mix", code, kwargs))
            return {"code": code}

    service = RoomService(FakeRepository())
    assert service.snapshot("room01")["code"] == "ROOM01"
    service.execute("room01", RoomCommand.from_payload("enqueue", {"song_id": "s1"}))
    assert calls == [("snapshot", "ROOM01"), ("enqueue", "ROOM01", "s1")]


def test_service_uses_store_room_semantics(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    song = store.create_song("测试", "歌手", "zh")
    store.update_song(song["id"], status="ready")

    snap = room_service.execute(
        "ROOM01",
        RoomCommand.from_payload("enqueue", {"song_id": song["id"]}),
    )

    assert snap["code"] == "ROOM01"
    assert snap["now_playing"]["song_id"] == song["id"]
