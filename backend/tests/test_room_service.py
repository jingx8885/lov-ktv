import pytest

from lovktv.room_service import RoomCommand, room_service
from lovktv.room_service import RoomService
from lovktv.room_store import SqliteRoomStore
from lovktv.contracts import RoomAction, RoomSnapshot
from lovktv.room_contract import normalize_playback_event, normalize_room_code
from lovktv.timeline_contract import normalize_timeline


def test_sqlite_adapter_persists_optional_lan_metadata(monkeypatch, tmp_path):
    # The adapter now owns the implementation instead of forwarding to store.
    from lovktv import store
    store.DB_PATH = tmp_path / "room.sqlite"
    store.init_db()
    snap = SqliteRoomStore().set_room_lan("r1", "http://192.168.1.2:8790", 9000, 48000)
    assert snap["code"] == "R1"
    assert snap["lan_mic_port"] == 9000


def test_room_contracts_keep_transport_action_and_snapshot_shape():
    action: RoomAction = "mix"
    snapshot: RoomSnapshot = {"code": "R1", "queue": [], "now_playing": None, "now_index": 0}
    assert action == "mix"
    assert snapshot["code"] == "R1"


def test_runtime_contract_normalizes_code_and_rejects_bad_code():
    assert normalize_room_code(" r1-a ") == "R1-A"
    with pytest.raises(ValueError, match="房间号无效"):
        normalize_room_code("bad room")


def test_timeline_contract_clamps_and_orders_cues_and_tokens():
    doc = normalize_timeline({
        "cues": [
            {"text": " second ", "start_ms": -4, "end_ms": 10,
             "tokens": [{"text": "x", "start_ms": -2, "end_ms": 99}]},
            {"text": "first", "start_ms": 20, "end_ms": 10, "tokens": []},
        ]
    })
    assert [cue["text"] for cue in doc["cues"]] == ["second", "first"]
    assert doc["cues"][0]["start_ms"] == 0
    assert doc["cues"][0]["tokens"][0]["end_ms"] == 10


def test_playback_event_requires_target_for_jump_commands():
    assert normalize_playback_event("skip", {})["action"] == "skip"
    assert normalize_playback_event("play", {"song_id": 123})["song_id"] == "123"
    with pytest.raises(ValueError, match="缺少目标"):
        normalize_playback_event("bump", {})


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
