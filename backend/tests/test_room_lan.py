import pytest
from fastapi.testclient import TestClient

from lovktv.room_store import normalize_lan_origin, set_room_lan


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.delenv("LOVKTV_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main.app, store


def test_normalize_lan_origin_accepts_private_http():
    assert normalize_lan_origin("http://192.168.1.8:8788") == "http://192.168.1.8:8788"
    assert normalize_lan_origin("192.168.1.8:8788/") == "http://192.168.1.8:8788"
    assert normalize_lan_origin("http://10.0.0.4:90") == "http://10.0.0.4:90"


def test_normalize_lan_origin_rejects_public_and_https():
    with pytest.raises(ValueError, match="局域网地址无效"):
        normalize_lan_origin("https://ktv.lovbrowser.com")
    with pytest.raises(ValueError, match="局域网地址无效"):
        normalize_lan_origin("http://ktv.lovbrowser.com:8788")
    with pytest.raises(ValueError, match="局域网地址无效"):
        normalize_lan_origin("http://192.168.1.8:8788/m.html")


def test_set_room_lan_persists_on_snapshot(tmp_path, monkeypatch):
    _app(tmp_path, monkeypatch)
    from lovktv.room_store import room_snapshot

    snap = set_room_lan(
        "home01", "http://192.168.1.8:8788", mic_port=18787, mic_sample_rate=48000
    )
    assert snap["code"] == "HOME01"
    assert snap["lan_origin"] == "http://192.168.1.8:8788"
    assert int(snap["lan_mic_port"]) == 18787
    assert int(snap["lan_mic_sample_rate"]) == 48000
    assert int(snap["lan_seen_at"]) > 0
    again = room_snapshot("HOME01")
    assert again["lan_origin"] == "http://192.168.1.8:8788"


def test_phone_can_read_lan_from_room_code(tmp_path, monkeypatch):
    app, _store = _app(tmp_path, monkeypatch)
    with TestClient(app) as tv:
        posted = tv.post(
            "/api/rooms/EABAB5/lan",
            json={
                "local_url": "http://192.168.5.6:8788",
                "mic_port": 18787,
                "mic_sample_rate": 48000,
            },
        )
    assert posted.status_code == 200
    body = posted.json()
    assert body["code"] == "EABAB5"
    assert body["lan_origin"] == "http://192.168.5.6:8788"
    assert body["lan_mic_port"] == 18787
    with TestClient(app) as phone:
        got = phone.get("/api/rooms/EABAB5")
    assert got.status_code == 200
    assert got.json()["lan_origin"] == "http://192.168.5.6:8788"
    assert got.json()["lan_mic_port"] == 18787


def test_room_lan_rejects_public_origin(tmp_path, monkeypatch):
    app, _store = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        bad = client.post(
            "/api/rooms/EABAB5/lan", json={"lan_origin": "https://example.com"}
        )
    assert bad.status_code == 400
