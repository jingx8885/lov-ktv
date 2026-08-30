from fastapi.testclient import TestClient


def _init(store, tmp_path):
    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()


def test_register_bonus_ad_and_costs(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.identity import ads as ads_mod
    from lovktv.routers import songs
    from lovktv.storage import store

    _init(store, tmp_path)
    monkeypatch.setattr(songs, "spawn", lambda *args, **kwargs: None)
    monkeypatch.setattr(ads_mod, "AD_MIN_MS", 0)
    from lovktv.main import app

    headers = {"X-LovKtv-Machine": "phone-machine-01"}
    with TestClient(app) as client:
        started = client.post(
            "/api/ads/start", json={"placement": "splash"}, headers=headers
        )
        assert started.status_code == 200
        token = started.json()["token"]
        assert started.json()["ad"]["url"]
        done = client.post("/api/ads/complete", json={"token": token}, headers=headers)
        assert done.status_code == 200
        assert done.json()["points"]["balance"] == 1
        again_ad = client.post("/api/ads/complete", json={"token": token}, headers=headers)
        assert again_ad.status_code == 409
        click = client.post("/api/ads/click", json={"token": token}, headers=headers)
        assert click.status_code == 200
        assert "http" in click.json()["url"] or click.json()["url"].startswith("/")

        created = client.post(
            "/api/auth/register",
            json={"username": "room9", "password": "pass"},
            headers=headers,
        )
        assert created.status_code == 200
        assert created.json()["points"]["balance"] >= 10
        song = store.create_song("晴天", "周杰伦", "zh")
        store.update_song(song["id"], status="ready")
        room = client.post("/api/rooms").json()["code"]
        queued = client.post(
            f"/api/rooms/{room}/queue", json={"song_id": song["id"]}
        )
        assert queued.status_code == 200
        after = client.get("/api/points").json()["balance"]
        assert after == created.json()["points"]["balance"] - 1
        claim = client.post("/api/points/claim", json={"kind": "download"})
        assert claim.status_code == 200
        again = client.post("/api/points/claim", json={"kind": "download"})
        assert again.status_code == 409
