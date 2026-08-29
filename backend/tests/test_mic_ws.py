from fastapi.testclient import TestClient


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import host_volume, main, runtime, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    runtime._rooms.clear()
    runtime._peers.clear()
    runtime._mics.clear()
    host_volume._cached = None
    return main, store


def test_set_mix_clamps_volume_and_mic_gain(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import room_store, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    room_store.ensure_room("MIX1")
    snap = room_store.set_mix("MIX1", vocal_mix=2, volume=140, mic_gain=-8)
    assert snap["vocal_mix"] == 1
    assert snap["volume"] == 100
    assert snap["mic_gain"] == 0
    snap = room_store.set_mix("MIX1", paused=True)
    assert int(snap["paused"]) == 1
    snap = room_store.set_mix("MIX1", paused=False)
    assert int(snap["paused"]) == 0


def test_mix_http_sets_mac_volume_and_snapshot(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    applied = []
    from lovktv.services import room_runtime

    monkeypatch.setattr(
        room_runtime, "set_host_volume", lambda volume: applied.append(volume) or True
    )
    monkeypatch.setattr(
        room_runtime,
        "host_volume_meta",
        lambda: {"host_volume_kind": "mac", "host_volume": 35},
    )
    from lovktv import room_store

    room_store.ensure_room("MAC1")
    with TestClient(main.app) as client:
        res = client.post("/api/rooms/MAC1/mix", json={"volume": 35, "mic_gain": 60})
        assert res.status_code == 200
        body = res.json()
        assert body["volume"] == 35
        assert body["mic_gain"] == 60
        assert body["host_volume_kind"] == "mac"
        assert body["mic_on"] is False
        assert applied == [35]


def test_ws_relays_rtc_and_marks_mic(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    from lovktv.services import room_runtime

    monkeypatch.setattr(room_runtime, "host_volume_meta", lambda: {})
    from lovktv import room_store

    room_store.ensure_room("MIC1")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/rooms/MIC1") as phone:
            assert phone.receive_json()["type"] == "snapshot"
            with client.websocket_connect("/ws/rooms/MIC1") as tv:
                assert tv.receive_json()["type"] == "snapshot"
                phone.send_json({"action": "hello", "role": "phone", "peer": "p-phone"})
                join = tv.receive_json()
                assert join["type"] == "peer"
                assert join["role"] == "phone"
                phone.send_json(
                    {
                        "action": "rtc",
                        "kind": "offer",
                        "from": "p-phone",
                        "sdp": {"type": "offer", "sdp": "x"},
                    }
                )
                rtc = tv.receive_json()
                assert rtc["type"] == "rtc"
                assert rtc["kind"] == "offer"
                assert rtc["sdp"]["sdp"] == "x"
                snap = tv.receive_json()
                assert snap["type"] == "snapshot"
                assert snap["room"]["mic_on"] is True
                assert snap["room"]["mic_peer"] == "p-phone"
                phone.send_json({"action": "rtc", "kind": "hangup", "from": "p-phone"})
                hang = tv.receive_json()
                assert hang["kind"] == "hangup"
                off = tv.receive_json()
                assert off["room"]["mic_on"] is False
