from fastapi.testclient import TestClient

from lovktv.auth import decode_state, encode_state, scan_login_url, wechat_authorize_url


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


def test_wechat_silent_authorize_uses_snsapi_base(monkeypatch):
    from lovktv import auth

    monkeypatch.setattr(auth, "WECHAT_MP_APP_ID", "mp-app")
    monkeypatch.setattr(auth, "WECHAT_MP_APP_SECRET", "mp-secret")
    url = wechat_authorize_url("http://127.0.0.1/cb", "silent|abc|", silent=True)
    assert "snsapi_base" in url
    assert "oauth2/authorize" in url
    assert "mp-app" in url


def test_scan_login_url_points_at_scan():
    url = scan_login_url("http://192.168.1.8:8787", ticket="abc123", room="EABAB5")
    assert url == "http://192.168.1.8:8787/api/auth/scan?ticket=abc123&room=EABAB5"


def test_qr_login_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    _init(store, tmp_path)
    user = store.upsert_device_user("phone-device-01", "小明")
    assert user["nickname"] == "小明"
    assert user["wechat"] is False
    assert len(user["sid"]) == 6
    again = store.upsert_wechat_user("wx-openid-stable")
    same = store.upsert_wechat_user("wx-openid-stable", nickname="忽略")
    assert again["id"] == same["id"]
    assert again["sid"] == same["sid"]
    assert again["wechat"] is True
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
        assert "/api/auth/scan" in created["url"]
        assert "ticket=" in created["url"]
        scan = phone.get(f"/api/auth/scan?ticket={ticket}&room=EABAB5", follow_redirects=False)
        assert scan.status_code == 302
        assert "/login.html" in scan.headers["location"]
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
        assert device.json()["user"]["sid"]
        assert phone.get("/api/auth/me").json()["user"]["nickname"] == "小明"
        auto = phone.get(f"/api/auth/scan?ticket={ticket}&room=EABAB5", follow_redirects=False)
        assert auto.status_code == 302
        assert phone.get(f"/api/auth/qr/{ticket}").json()["status"] == "confirmed"

    with TestClient(app) as tv:
        pending = tv.get(f"/api/auth/qr/{ticket}").json()
        assert pending["status"] == "confirmed"
        claimed = tv.get(f"/api/auth/qr/{ticket}?claim=1").json()
        assert claimed["status"] == "ok"
        assert claimed["user"]["nickname"] == "小明"
        assert tv.get("/api/auth/me").json()["user"]["nickname"] == "小明"
        again = tv.get(f"/api/auth/qr/{ticket}?claim=1").json()
        assert again["status"] == "used"


def test_scan_in_wechat_goes_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import auth, store

    _init(store, tmp_path)
    monkeypatch.setattr(auth, "WECHAT_MP_APP_ID", "mp-app")
    monkeypatch.setattr(auth, "WECHAT_MP_APP_SECRET", "mp-secret")
    from lovktv.main import app

    with TestClient(app) as client:
        created = client.post("/api/auth/qr", json={"room": "B0EBAE"}).json()
        res = client.get(
            f"/api/auth/scan?ticket={created['ticket']}",
            headers={"User-Agent": "Mozilla/5.0 MicroMessenger/8.0"},
            follow_redirects=False,
        )
        assert res.status_code == 302
        loc = res.headers["location"]
        assert "open.weixin.qq.com" in loc
        assert "snsapi_base" in loc
