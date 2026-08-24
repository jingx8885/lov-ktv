from fastapi.testclient import TestClient

from lovktv.auth import decode_state, encode_state, wechat_authorize_url


def _init(store, tmp_path):
    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()


def test_encode_state_roundtrip():
    state = encode_state("quick", "abc123", "/m.html?room=EABAB5")
    assert decode_state(state) == ("quick", "abc123", "/m.html?room=EABAB5")


def test_wechat_authorize_requires_app_id(monkeypatch):
    from lovktv import auth

    monkeypatch.setattr(auth, "WECHAT_APP_ID", "")
    monkeypatch.setattr(auth, "WECHAT_APP_SECRET", "")
    try:
        wechat_authorize_url("http://127.0.0.1/cb", "web")
        raise AssertionError("should fail")
    except ValueError as exc:
        assert "AppID" in str(exc)


def test_qr_login_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    _init(store, tmp_path)
    user = store.upsert_device_user("phone-device-01", "小明")
    assert user["nickname"] == "小明"
    assert user["wechat"] is False
    ticket = store.create_login_ticket()
    store.confirm_login_ticket(ticket["ticket"], user["id"])
    claimed = store.consume_confirmed_ticket(ticket["ticket"])
    assert claimed["id"] == user["id"]
    assert store.consume_confirmed_ticket(ticket["ticket"]) is None


def test_expired_ticket_cannot_confirm(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    _init(store, tmp_path)
    user = store.upsert_device_user("phone-device-02", "阿强")
    ticket = store.create_login_ticket(ttl_ms=-5)
    row = store.get_login_ticket(ticket["ticket"])
    assert row["status"] == "expired"
    try:
        store.confirm_login_ticket(ticket["ticket"], user["id"])
        raise AssertionError("should fail")
    except ValueError as exc:
        assert "过期" in str(exc)


def test_qr_login_http_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    _init(store, tmp_path)
    from lovktv.main import app

    with TestClient(app) as phone:
        created = phone.post("/api/auth/qr", json={"room": "EABAB5"}).json()
        ticket = created["ticket"]
        assert "login=" in created["url"]
        assert phone.get("/api/auth/me").json()["user"] is None
        bad = phone.post("/api/auth/device", json={"device_id": "short"})
        assert bad.status_code == 400
        denied = phone.post(f"/api/auth/qr/{ticket}/confirm")
        assert denied.status_code == 401
        wechat = phone.get("/api/auth/wechat/login", follow_redirects=False)
        assert wechat.status_code == 400
        device = phone.post(
            "/api/auth/device",
            json={"device_id": "phone-device-99", "nickname": "小明"},
        )
        assert device.status_code == 200
        assert device.json()["user"]["nickname"] == "小明"
        assert phone.get("/api/auth/me").json()["user"]["nickname"] == "小明"
        ok = phone.post(f"/api/auth/qr/{ticket}/confirm")
        assert ok.status_code == 200

    with TestClient(app) as tv:
        pending = tv.get(f"/api/auth/qr/{ticket}").json()
        assert pending["status"] == "confirmed"
        claimed = tv.get(f"/api/auth/qr/{ticket}?claim=1").json()
        assert claimed["status"] == "ok"
        assert claimed["user"]["nickname"] == "小明"
        assert tv.get("/api/auth/me").json()["user"]["nickname"] == "小明"
        again = tv.get(f"/api/auth/qr/{ticket}?claim=1").json()
        assert again["status"] == "used"
