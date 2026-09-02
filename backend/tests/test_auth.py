from fastapi.testclient import TestClient

from lovktv.identity.auth import (
    decode_state,
    encode_state,
    scan_login_url,
    wechat_authorize_url,
)


def _init(store, tmp_path):
    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()


def test_encode_state_roundtrip():
    state = encode_state("quick", "abc123", "/m.html?room=EABAB5")
    assert decode_state(state) == ("quick", "abc123", "/m.html?room=EABAB5")


def test_wechat_authorize_requires_app_id(monkeypatch):
    from lovktv.identity import auth

    monkeypatch.setattr(auth, "WECHAT_APP_ID", "")
    monkeypatch.setattr(auth, "WECHAT_APP_SECRET", "")
    try:
        wechat_authorize_url("http://127.0.0.1/cb", "web")
        raise AssertionError("should fail")
    except ValueError as exc:
        assert "AppID" in str(exc)


def test_wechat_silent_authorize_uses_snsapi_base(monkeypatch):
    from lovktv.identity import auth

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
    from lovktv.storage import store

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
    from lovktv.storage import store

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
    from lovktv.storage import store

    _init(store, tmp_path)
    from lovktv.main import app

    with TestClient(app) as phone:
        created = phone.post("/api/auth/qr", json={"room": "EABAB5"}).json()
        ticket = created["ticket"]
        assert "/api/auth/scan" in created["url"]
        assert "ticket=" in created["url"]
        scan = phone.get(
            f"/api/auth/scan?ticket={ticket}&room=EABAB5", follow_redirects=False
        )
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
        auto = phone.get(
            f"/api/auth/scan?ticket={ticket}&room=EABAB5", follow_redirects=False
        )
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
    from lovktv.identity import auth
    from lovktv.storage import store

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


def test_password_register_login_and_casefold(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import store

    _init(store, tmp_path)
    from lovktv.main import app

    with TestClient(app) as client:
        status = client.get("/api/auth/status").json()
        assert status["password"] is True
        assert status["guest_limit"] == 5
        me = client.get("/api/auth/me").json()
        assert me["user"] is None
        assert me["quota"]["unlimited"] is False
        assert me["quota"]["remaining"] == 5
        bad = client.post("/api/auth/register", json={"username": "ab", "password": "1"})
        assert bad.status_code == 400
        created = client.post(
            "/api/auth/register", json={"username": "EABAB5", "password": "1234"}
        )
        assert created.status_code == 200
        user = created.json()["user"]
        assert user["username"] == "EABAB5"
        assert user["account"] is True
        assert "password_hash" not in user
        assert client.get("/api/auth/me").json()["user"]["username"] == "EABAB5"
        taken = client.post(
            "/api/auth/register", json={"username": "eabab5", "password": "abcd"}
        )
        assert taken.status_code == 400
        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").json()["user"] is None
        wrong = client.post(
            "/api/auth/login", json={"username": "EABAB5", "password": "nope"}
        )
        assert wrong.status_code == 400
        again = client.post(
            "/api/auth/login", json={"username": "eabab5", "password": "1234"}
        )
        assert again.status_code == 200
        assert again.json()["user"]["username"] == "EABAB5"
        assert again.json()["quota"]["unlimited"] is True


def test_session_cookie_not_secure_on_plaintext_origin(tmp_path, monkeypatch):
    """A https public URL must not put `Secure` on a plaintext LAN/TV reply.

    The browser silently drops such a cookie, which showed up as the TV and
    the LAN phone desk asking for a fresh login on every page load.
    """
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.setenv("LOVKTV_PUBLIC_URL", "https://ktv.lovbrowser.com")
    from lovktv.storage import store

    _init(store, tmp_path)
    from lovktv.main import app

    with TestClient(app, base_url="http://192.168.1.8:8787") as lan:
        res = lan.post(
            "/api/auth/device",
            json={"device_id": "lan-device-01", "nickname": "局域网"},
        )
        assert res.status_code == 200
        assert "secure" not in res.headers["set-cookie"].lower()
        # The cookie actually survives the round trip, so login sticks.
        assert lan.get("/api/auth/me").json()["user"]["nickname"] == "局域网"


def test_session_cookie_secure_behind_tls_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import store

    _init(store, tmp_path)
    from lovktv.main import app

    with TestClient(app, base_url="http://127.0.0.1:8787") as client:
        res = client.post(
            "/api/auth/device",
            json={"device_id": "tls-device-01", "nickname": "代理"},
            headers={"X-Forwarded-Proto": "https"},
        )
        assert res.status_code == 200
        assert "Secure" in res.headers["set-cookie"]


def test_session_slides_forward_past_half_life(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import store

    _init(store, tmp_path)
    user = store.upsert_device_user("slide-device-01", "常客")
    token = store.create_session(user["id"], days=30)
    window = 30 * 86400_000

    def expiry() -> int:
        with store.connect() as conn:
            row = store.execute(
                conn, "SELECT expires_at FROM sessions WHERE token=?", (token,)
            ).fetchone()
        return int(row["expires_at"])

    # Fresh session: nothing to do, so no write and nothing to re-stamp.
    fresh = expiry()
    assert store.refresh_session(token, 30) == 0
    assert expiry() == fresh

    # Aged past the half-life: the window slides forward.
    with store.connect() as conn:
        store.execute(
            conn,
            "UPDATE sessions SET expires_at=? WHERE token=?",
            (store.now_ms() + 86400_000, token),
        )
    slid = store.refresh_session(token, 30)
    assert slid > fresh
    assert slid >= store.now_ms() + window - 5_000
    assert store.user_from_session(token)["id"] == user["id"]

    # Already-expired and unknown tokens are never resurrected.
    with store.connect() as conn:
        store.execute(
            conn,
            "UPDATE sessions SET expires_at=? WHERE token=?",
            (store.now_ms() - 1, token),
        )
    assert store.refresh_session(token, 30) == 0
    assert store.refresh_session("no-such-token", 30) == 0


def test_auth_me_renews_long_lived_session(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import store

    _init(store, tmp_path)
    from lovktv.main import app

    with TestClient(app) as client:
        assert (
            client.post(
                "/api/auth/device",
                json={"device_id": "renew-device-01", "nickname": "回头客"},
            ).status_code
            == 200
        )
        token = client.cookies["lovktv_session"]
        with store.connect() as conn:
            store.execute(
                conn,
                "UPDATE sessions SET expires_at=? WHERE token=?",
                (store.now_ms() + 86400_000, token),
            )
        res = client.get("/api/auth/me")
        assert res.json()["user"]["nickname"] == "回头客"
        # Same token, pushed further out: the user is not logged out on day 30.
        assert "lovktv_session" in res.headers.get("set-cookie", "")
        assert client.cookies["lovktv_session"] == token
        with store.connect() as conn:
            row = store.execute(
                conn, "SELECT expires_at FROM sessions WHERE token=?", (token,)
            ).fetchone()
        assert int(row["expires_at"]) > store.now_ms() + 20 * 86400_000


def test_guest_song_quota_then_login_unlimited(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.routers import songs
    from lovktv.storage import store

    _init(store, tmp_path)
    monkeypatch.setattr(songs, "spawn", lambda *args, **kwargs: None)
    from lovktv.identity import points as points_mod

    monkeypatch.setattr(points_mod, "POINTS_ENFORCED", True)
    from lovktv.main import app

    with TestClient(app) as guest:
        for i in range(5):
            res = guest.post(
                "/api/songs/import",
                json={"query": f"song {i}", "title": f"song {i}"},
            )
            assert res.status_code == 200, res.text
        blocked = guest.post(
            "/api/songs/import", json={"query": "song 6", "title": "song 6"}
        )
        assert blocked.status_code == 402
        me = guest.get("/api/auth/me").json()
        assert me["quota"]["remaining"] == 0
        registered = guest.post(
            "/api/auth/register", json={"username": "room1", "password": "pass"}
        )
        assert registered.status_code == 200
        assert registered.json()["quota"]["unlimited"] is True
        assert registered.json()["points"]["balance"] == 10
        extra = guest.post(
            "/api/songs/import", json={"query": "song 7", "title": "song 7"}
        )
        assert extra.status_code == 200
