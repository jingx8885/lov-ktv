from fastapi.testclient import TestClient


def _boot(tmp_path, monkeypatch, token="admin-secret"):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    if token is None:
        monkeypatch.delenv("LOVKTV_ADMIN_TOKEN", raising=False)
        monkeypatch.delenv("LOVKTV_APP_UPLOAD_TOKEN", raising=False)
    else:
        monkeypatch.setenv("LOVKTV_ADMIN_TOKEN", token)
    from lovktv import main
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main, store


def test_admin_requires_token(tmp_path, monkeypatch):
    main, _store = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        denied = client.get("/api/admin/summary")
        wrong = client.post("/api/admin/login", json={"token": "nope"})
        page = client.get("/admin.html")
    assert denied.status_code == 401
    assert wrong.status_code == 401
    assert "admin-secret" not in denied.text
    assert "admin-secret" not in wrong.text
    assert page.status_code == 200
    assert 'src="/admin/js/admin.js' in page.text


def test_admin_missing_config(tmp_path, monkeypatch):
    main, _store = _boot(tmp_path, monkeypatch, token=None)
    with TestClient(main.app) as client:
        resp = client.post("/api/admin/login", json={"token": "x"})
    assert resp.status_code == 503


def test_admin_deduct_and_add_points(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        user = client.post(
            "/api/auth/register", json={"username": "room8", "password": "pass"}
        ).json()["user"]
        login = client.post("/api/admin/login", json={"token": "admin-secret"})
        assert login.status_code == 200
        me = client.get("/api/admin/me")
        assert me.status_code == 200
        found = client.get("/api/admin/points?q=room8").json()
        assert found["account"]["balance"] == 10
        assert found["account"]["user"]["username"] == "room8"
        cut = client.post(
            "/api/admin/points",
            json={"username": "room8", "delta": -3, "note": "包厢结算"},
        )
        assert cut.status_code == 200
        assert cut.json()["balance"] == 7
        assert cut.json()["ledger"][0]["kind"] == "admin"
        assert cut.json()["ledger"][0]["delta"] == -3
        add = client.post(
            "/api/admin/points",
            json={"owner": "u:" + user["id"], "delta": 2, "note": "补分"},
        )
        assert add.status_code == 200
        assert add.json()["balance"] == 9
        too_much = client.post(
            "/api/admin/points", json={"username": "room8", "delta": -99}
        )
        assert too_much.status_code == 400
        users = client.get("/api/admin/users?q=room8").json()["users"]
        assert users[0]["balance"] == 9
        assert client.get("/api/admin/songs").status_code == 200
        assert client.get("/api/admin/rooms").status_code == 200
        assert client.get("/api/admin/ads").status_code == 200
        summary = client.get("/api/admin/summary").json()
        assert summary["rules"]["process_cost"] == 5
        assert summary["rules"]["queue_cost"] == 1
        settings = client.get("/api/admin/settings")
        assert settings.status_code == 200
        saved = client.post("/api/admin/settings", json={"settings": {"queue_cost": 3}})
        assert saved.status_code == 200
        assert next(item for item in saved.json()["settings"] if item["key"] == "queue_cost")["value"] == 3
        store.create_song("晴天", "周杰伦", "zh")
        songs = client.get("/api/admin/songs").json()["songs"]
        assert songs[0]["title"] == "晴天"
        edited = client.post(
            "/api/admin/songs/" + songs[0]["id"],
            json={"title": "晴天现场", "artist": "周杰伦"},
        )
        assert edited.status_code == 200
        assert edited.json()["title"] == "晴天现场"
        gone = client.delete("/api/admin/songs/" + songs[0]["id"])
        assert gone.status_code == 200
        pay = client.post(
            "/api/admin/recharge",
            json={"username": "room8", "amount": 50, "note": "现金"},
        )
        assert pay.status_code == 200
        assert pay.json()["balance"] == 59
        assert pay.json()["ledger"][0]["kind"] == "recharge"
        history = client.get("/api/admin/recharges").json()["recharges"]
        assert history[0]["delta"] == 50
        created = client.post(
            "/api/admin/users",
            json={"username": "box1", "password": "pass", "nickname": "一号包厢"},
        )
        assert created.status_code == 200
        assert created.json()["nickname"] == "一号包厢"
        assert created.json()["balance"] == 0
        renamed = client.post(
            "/api/admin/users/" + created.json()["id"],
            json={"nickname": "大厅"},
        )
        assert renamed.json()["nickname"] == "大厅"
        opened = client.post("/api/admin/rooms", json={"code": "HALL01"})
        assert opened.status_code == 200
        assert opened.json()["code"] == "HALL01"
        listed = client.get("/api/admin/rooms?q=HALL").json()["rooms"]
        assert listed[0]["code"] == "HALL01"
        song = store.create_song("七里香", "周杰伦", "zh")
        store.update_song(song["id"], status="ready")
        queued = client.post(
            "/api/admin/rooms/HALL01/queue", json={"song_id": song["id"]}
        )
        assert queued.status_code == 200
        assert queued.json()["queue"][0]["song_id"] == song["id"]
        detail = client.get("/api/admin/rooms/HALL01").json()
        item_id = detail["queue"][0]["id"]
        client.post("/api/admin/rooms/HALL01/bump", json={"id": item_id})
        cleared = client.post("/api/admin/rooms/HALL01/clear")
        assert cleared.json()["queue"] == []
        gone_room = client.delete("/api/admin/rooms/HALL01")
        assert gone_room.status_code == 200
        assert client.get("/api/admin/rooms/HALL01").status_code == 404
        client.post("/api/admin/logout")
        assert client.get("/api/admin/me").status_code == 401
