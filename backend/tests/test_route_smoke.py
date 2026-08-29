from fastapi.testclient import TestClient


def test_public_route_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, store

    store.DB_PATH = tmp_path / "smoke.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    with TestClient(main.app) as client:
        host = client.get("/api/host")
        assert host.status_code == 200
        assert {"origin", "models", "database"} <= host.json().keys()
        assert client.get("/api/auth/status").status_code == 200
        assert client.get("/m.html").status_code == 200
        assert client.get("/tv.html").status_code == 200


def test_room_websocket_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, room_store, runtime, store

    store.DB_PATH = tmp_path / "smoke.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    room_store.ensure_room("SMOKE1")
    runtime._rooms.clear()
    runtime._peers.clear()
    runtime._mics.clear()
    with (
        TestClient(main.app) as client,
        client.websocket_connect("/ws/rooms/SMOKE1") as ws,
    ):
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert msg["room"]["code"] == "SMOKE1"
