import json

from fastapi.testclient import TestClient


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "billing.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return store


def test_paid_quota_is_monthly_and_enforced(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    from lovktv.main import app

    with TestClient(app) as client:
        user = client.post(
            "/api/auth/register", json={"username": "payer", "password": "pass"}
        ).json()["user"]
        store.update_billing_user(user["id"], plan="starter", plan_status="active")
        current = client.get("/api/auth/me").json()["quota"]
        assert current["limit"] == 100
        assert current["remaining"] == 100
        for _ in range(100):
            assert store.consume_song_quota(
                "u:" + user["id"], "month:" + current["period"], 100
            )
        assert not store.consume_song_quota(
            "u:" + user["id"], "month:" + current["period"], 100
        )


def test_billing_webhook_is_idempotent(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    import lovktv.routers.billing as billing
    from lovktv.main import app

    billing.STRIPE_WEBHOOK_SECRET = ""
    user = store.register_password_user("payer", "pass")
    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": user["id"],
                "payment_status": "paid",
                "metadata": {"plan": "pro"},
                "customer": "cus_1",
                "subscription": "sub_1",
            }
        },
    }
    with TestClient(app) as client:
        first = client.post(
            "/api/billing/webhook",
            content=json.dumps(event),
            headers={"content-type": "application/json"},
        )
        second = client.post(
            "/api/billing/webhook",
            content=json.dumps(event),
            headers={"content-type": "application/json"},
        )
    assert first.status_code == 200
    assert second.json()["duplicate"] is True
    assert store.get_user(user["id"])["plan"] == "pro"


def test_admin_identity_is_unrestricted_for_username_and_google_email(
    tmp_path, monkeypatch
):
    store = _setup(tmp_path, monkeypatch)
    from lovktv.identity.plans import effective_plan, processing_priority
    from lovktv.identity.song_admin import is_unrestricted_admin

    password_admin = store.register_password_user("jingxu8885", "pass")
    google_admin = store.upsert_google_user(
        "google-admin-sub", "jingxu8885@gmail.com", "管理员"
    )

    assert is_unrestricted_admin(password_admin) is True
    assert is_unrestricted_admin(google_admin) is True
    assert google_admin["admin"] is True
    assert effective_plan(password_admin) == "admin"
    assert effective_plan(google_admin) == "admin"
    assert processing_priority(password_admin) > processing_priority({"plan": "pro"})


def test_admin_quota_and_rooms_are_unlimited_and_queue_cost_is_skipped(
    tmp_path, monkeypatch
):
    store = _setup(tmp_path, monkeypatch)
    from lovktv.identity import points as points_mod
    from lovktv.main import app
    from lovktv.storage.room_store import count_user_rooms

    song = store.create_song("晴天", "周杰伦", "zh")
    store.update_song(song["id"], status="ready")
    monkeypatch.setattr(
        points_mod,
        "_setting",
        lambda key: {"points_enabled": True, "queue_cost": 1}.get(key, 0),
    )

    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register", json={"username": "jingxu8885", "password": "pass"}
        )
        assert registered.status_code == 200
        assert registered.json()["user"]["admin"] is True
        quota = client.get("/api/auth/me").json()["quota"]
        assert quota["unlimited"] is True
        assert quota["plan"] == "admin"

        for index in range(7):
            client.cookies.delete("lovktv_host")
            room = client.post(
                "/api/rooms",
                headers={
                    "X-LovKtv-Machine": f"admin-machine-{index:02d}",
                    "User-Agent": f"admin-browser-{index:02d}",
                },
            )
            assert room.status_code == 200
        assert count_user_rooms(registered.json()["user"]["id"]) == 7

        balance_before = client.get("/api/points").json()["balance"]
        queued = client.post(
            f"/api/rooms/{room.json()['code']}/queue", json={"song_id": song["id"]}
        )
        assert queued.status_code == 200
        assert client.get("/api/points").json()["balance"] == balance_before

def test_apple_login_accepts_signed_token(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    import lovktv.routers.billing as billing
    from lovktv.main import app
    from Crypto.PublicKey import RSA
    from Crypto.Signature import pkcs1_15
    from Crypto.Hash import SHA256
    import base64, json, time

    # 造一份本地 RSA key + 合法 Apple JWT，预置进 JWKS 缓存绕过外网
    key = RSA.generate(2048)
    pub = key.publickey()
    jwk = {
        "kty": "RSA", "kid": "test-kid", "use": "sig", "alg": "RS256",
        "n": base64.urlsafe_b64encode(pub.n.to_bytes(256, "big")).rstrip(b"=").decode(),
        "e": base64.urlsafe_b64encode(pub.e.to_bytes(3, "big")).rstrip(b"=").decode(),
    }
    billing._apple_keys_cache["jwks"] = (time.time() + 3600, {"keys": [jwk]})
    billing.APPLE_CLIENT_ID = "com.lovktv.phone"

    claims = {
        "iss": "https://appleid.apple.com", "aud": "com.lovktv.phone",
        "sub": "001234.testapplesub", "email": "apple@example.com",
        "exp": int(time.time()) + 3600, "iat": int(time.time()),
    }
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "kid": "test-kid"}).encode()).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = base64.urlsafe_b64encode(pkcs1_15.new(key).sign(SHA256.new(signing_input))).rstrip(b"=").decode()
    token = f"{header_b64}.{payload_b64}.{signature}"

    with TestClient(app) as client:
        resp = client.post("/api/auth/apple", json={"identity_token": token})
        assert resp.status_code == 200, resp.text
        user = resp.json()["user"]
        assert user["email"] == "apple@example.com"
        assert resp.cookies.get("lovktv_session")
        # apple_sub 是内部绑定字段，不出现在对外 user 投影里
        assert store.execute(
            store.connect(),
            "SELECT apple_sub FROM users WHERE id=?",
            (user["id"],),
        ).fetchone()["apple_sub"] == "001234.testapplesub"

        # 同一 sub 再登返回同一账号
        again = client.post("/api/auth/apple", json={"identity_token": token})
        assert again.json()["user"]["id"] == user["id"]


def test_apple_login_rejects_bad_token(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import lovktv.routers.billing as billing
    from lovktv.main import app
    billing.APPLE_CLIENT_ID = "com.lovktv.phone"

    with TestClient(app) as client:
        resp = client.post("/api/auth/apple", json={"identity_token": "not-a-jwt"})
        assert resp.status_code == 401
