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
    spawn_ok = [True]

    def _spawn(*args, **kwargs):
        spawned.append((args, kwargs))
        return spawn_ok[0]

    monkeypatch.setattr("lovktv.routers.songs.spawn", _spawn)

    with TestClient(main.app) as client:
        ordinary = client.post(
            "/api/auth/register", json={"username": "singer", "password": "pass"}
        )
        assert ordinary.json()["user"]["admin"] is False
        assert client.get("/api/auth/me").json()["user"]["admin"] is False
        assert client.get("/api/songs").json()["songs"][0]["can_realign"] is False
        assert client.post(f"/api/songs/{song['id']}/realign", json={}).status_code == 403
        # Shared library deletion is a destructive admin action as well: a
        # plain member must not be able to wipe the catalog for everyone.
        assert client.delete(f"/api/songs/{song['id']}").status_code == 403
        assert store.get_song(song["id"]) is not None

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
        assert client.delete(f"/api/songs/{song['id']}").status_code == 200
        assert store.get_song(song["id"]) is None

        # A full queue rejects a second job: the endpoint reports the conflict
        # instead of pretending the work was queued.
        song2 = store.create_song("七里香", "周杰伦", "zh")
        store.update_song(song2["id"], status="ready")
        spawn_ok[0] = False
        assert client.post(f"/api/songs/{song2['id']}/realign", json={}).status_code == 409

    # The rejected conflict call still passes through the spawn stub, so the
    # log shows the accepted admin realign plus the 409 attempt on song2.
    assert len(spawned) == 2 and spawned[0][0][1] == song["id"]
