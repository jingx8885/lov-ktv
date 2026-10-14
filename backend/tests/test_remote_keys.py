import hashlib
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def context(tmp_path, monkeypatch):
    from lovktv.main import app
    from lovktv.storage import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "keys.sqlite")
    monkeypatch.setattr(store, "MEDIA_DIR", tmp_path / "media")
    store.init_db()
    with TestClient(app) as client:
        user = client.post(
            "/api/auth/register", json={"username": "keymember", "password": "pass"}
        ).json()["user"]
        yield client, store, user


def member_key(client, store, user):
    store.update_billing_user(user["id"], plan="pro", plan_status="active")
    response = client.post("/api/account/remote-key")
    assert response.status_code == 201
    return response.json()["api_key"]


def test_key_lifecycle_hash_only_and_account_isolation(context):
    client, store, user = context
    assert client.post("/api/account/remote-key").status_code == 403
    key = member_key(client, store, user)
    with store.connect() as conn:
        row = dict(store.execute(conn, "SELECT * FROM remote_api_keys").fetchone())
    assert row["key_hash"] == hashlib.sha256(key.encode()).hexdigest()
    assert key not in str(row)
    assert key not in client.get("/api/account/remote-key").text
    headers = {"Authorization": "Bearer " + key}
    assert client.get("/api/remote/ios/songs", headers=headers).status_code == 200
    replacement = member_key(client, store, user)
    assert client.get("/api/remote/ios/songs", headers=headers).status_code == 401
    client.post("/api/auth/logout")
    assert (
        client.get(
            "/api/account/remote-key",
            headers={"Authorization": "Bearer " + replacement},
        ).status_code
        == 401
    )
    client.post(
        "/api/auth/register", json={"username": "othermember", "password": "pass"}
    )
    assert client.get("/api/account/remote-key").json()["key"] is None
    client.delete("/api/account/remote-key")
    assert (
        client.get(
            "/api/remote/ios/songs", headers={"Authorization": "Bearer " + replacement}
        ).status_code
        == 200
    )
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "keymember", "password": "pass"})
    assert client.delete("/api/account/remote-key").status_code == 200
    assert (
        client.get(
            "/api/remote/ios/songs", headers={"Authorization": "Bearer " + replacement}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"plan_status": "canceled"},
        {"plan_status": "past_due"},
        {"plan": "free"},
        {"plan_expires_at": int(time.time() * 1000) - 1000},
    ],
)
def test_membership_rechecked_on_every_remote_route(context, fields):
    client, store, user = context
    key = member_key(client, store, user)
    store.update_billing_user(user["id"], **fields)
    headers = {"Authorization": "Bearer " + key}
    for method, path in [
        ("GET", "/songs"),
        ("GET", "/rooms/ABCD"),
        ("GET", "/media/test"),
        ("POST", "/rooms/ABCD/skip"),
        ("POST", "/reports"),
    ]:
        result = client.request(
            method, "/api/remote/ios" + path, headers=headers, json={}
        )
        assert result.status_code == 401
        assert result.json()["detail"] == "API key 无效或已失效"
    assert client.delete("/api/account/remote-key").status_code == 200


def test_ios_sources_are_filtered_for_library_queue_reports_and_media(context):
    client, store, user = context
    key = member_key(client, store, user)
    headers = {"Authorization": "Bearer " + key, "X-LovKTV-Platform": "ios"}
    owned = store.create_song("My recording", "Me", "en")
    store.update_song(owned["id"], status="ready", audio_source="upload")
    directory = store.MEDIA_DIR / owned["id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "original.mp3").write_bytes(b"owned-audio")
    from lovktv.storage.room_store import enqueue

    enqueue("ABCD", owned["id"])
    for source in [
        "netease",
        "youtube",
        "bilibili",
        "kugou",
        "soundcloud",
        "mugen",
        "",
        "unknown",
    ]:
        song = store.create_song(source or "legacy", "Public", "en")
        store.update_song(song["id"], status="ready", audio_source=source)
        enqueue("ABCD", song["id"])
        assert (
            client.post(
                "/api/remote/ios/rooms/ABCD/queue",
                headers=headers,
                json={"song_id": song["id"]},
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/remote/ios/reports",
                headers=headers,
                json={"song_id": song["id"], "reason": "test"},
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/remote/ios/media/" + song["id"], headers=headers
            ).status_code
            == 404
        )
    # Namespace remains restricted without a client platform hint.
    headers.pop("X-LovKTV-Platform")
    data = client.get("/api/remote/ios/songs?count=1", headers=headers).json()
    assert data["total"] == 1 and data["songs"][0]["id"] == owned["id"]
    assert (
        client.get("/api/remote/ios/songs?page=2&count=1", headers=headers).json()[
            "songs"
        ]
        == []
    )
    assert (
        client.get("/api/remote/ios/songs?q=missing", headers=headers).json()["total"]
        == 0
    )
    view = client.get("/api/remote/ios/rooms/ABCD", headers=headers).json()
    assert len(view["queue"]) == 1 and view["now_playing"]["song_id"] == owned["id"]
    assert (
        client.get("/api/remote/ios/media/" + owned["id"], headers=headers).content
        == b"owned-audio"
    )
    assert (
        client.post(
            "/api/remote/ios/reports",
            headers=headers,
            json={"song_id": owned["id"], "reason": "test"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/remote/ios/rooms/ABCD/mix", headers=headers, json={"volume": 30}
        ).json()["volume"]
        == 30
    )
    assert (
        client.post(
            "/api/remote/ios/rooms/ABCD/play",
            headers=headers,
            json={"item_id": "arbitrary"},
        ).status_code
        == 400
    )
    assert (
        client.get("/api/remote/ios/search?q=anything", headers=headers).status_code
        == 404
    )
    assert client.get("/api/remote/ios/songs").status_code == 401
    assert (
        client.get(
            "/api/remote/ios/songs", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    # Existing self-hosted / Android / web catalog retains every song.
    assert len(client.get("/api/songs").json()["songs"]) >= 9
