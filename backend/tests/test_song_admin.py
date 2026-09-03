from fastapi.testclient import TestClient


def test_song_admin_marker_and_realign_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    song = store.create_song("晴天", "周杰伦", "zh")
    store.update_song(song["id"], status="ready")
    spawned = []
    monkeypatch.setattr("lovktv.routers.songs.spawn", lambda *args, **kwargs: spawned.append((args, kwargs)))

    with TestClient(main.app) as client:
        ordinary = client.post(
            "/api/auth/register", json={"username": "singer", "password": "pass"}
        )
        assert ordinary.json()["user"]["admin"] is False
        assert client.get("/api/auth/me").json()["user"]["admin"] is False
        assert client.get("/api/songs").json()["songs"][0]["can_realign"] is False
        assert client.post(f"/api/songs/{song['id']}/realign", json={}).status_code == 403

        client.post("/api/auth/logout")
        admin = client.post(
            "/api/auth/register", json={"username": "jingxu8885", "password": "pass"}
        )
        assert admin.json()["user"]["admin"] is True
        assert client.get("/api/auth/me").json()["user"]["admin"] is True
        assert client.get("/api/songs").json()["songs"][0]["can_realign"] is True
        detail = client.get(f"/api/songs/{song['id']}").json()
        assert detail["can_realign"] is True
        assert client.post(f"/api/songs/{song['id']}/realign", json={}).status_code == 200

    assert spawned and spawned[0][0][1] == song["id"]
