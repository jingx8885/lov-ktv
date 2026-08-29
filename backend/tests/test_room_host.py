from fastapi.testclient import TestClient


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.delenv("LOVKTV_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from lovktv import main
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main.app, store


def test_same_machine_reuses_room(tmp_path, monkeypatch):
    app, _store = _app(tmp_path, monkeypatch)
    headers = {"User-Agent": "LovKtvAndroidTV/1", "X-LovKtv-Machine": "box-living-01"}
    with TestClient(app) as client:
        first = client.post("/api/rooms", headers=headers)
        second = client.post("/api/rooms", headers=headers)
    assert first.status_code == 200
    assert first.json()["code"] == second.json()["code"]
    assert len(first.json()["code"]) == 6


def test_ua_fallback_reuses_room_without_machine(tmp_path, monkeypatch):
    app, _store = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.cookies.clear()
        first = client.post("/api/rooms", headers={"User-Agent": "SmartTV/Chrome"})
        client.cookies.clear()
        second = client.post("/api/rooms", headers={"User-Agent": "SmartTV/Chrome"})
    assert first.json()["code"] == second.json()["code"]


def test_different_ua_gets_new_room(tmp_path, monkeypatch):
    app, _store = _app(tmp_path, monkeypatch)
    with TestClient(app) as tv:
        a = tv.post("/api/rooms", headers={"User-Agent": "TV-A"})
    with TestClient(app) as phone:
        b = phone.post("/api/rooms", headers={"User-Agent": "Phone-B"})
    assert a.json()["code"] != b.json()["code"]


def test_joining_a_room_binds_this_machine(tmp_path, monkeypatch):
    app, store = _app(tmp_path, monkeypatch)
    from lovktv.storage.room_store import ensure_room

    room = ensure_room("HOME01")
    headers = {"User-Agent": "iPhone", "X-LovKtv-Machine": "phone-alice-01"}
    with TestClient(app) as client:
        got = client.get("/api/rooms/" + room["code"], headers=headers)
        mine = client.get("/api/rooms", headers=headers)
        created = client.post("/api/rooms", headers=headers)
    assert got.json()["code"] == "HOME01"
    assert mine.json()["code"] == "HOME01"
    assert created.json()["code"] == "HOME01"


def test_unknown_machine_has_no_room(tmp_path, monkeypatch):
    app, _store = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        mine = client.get(
            "/api/rooms",
            headers={"User-Agent": "fresh-browser", "X-LovKtv-Machine": "brand-new-99"},
        )
    assert mine.json() == {"code": ""}
