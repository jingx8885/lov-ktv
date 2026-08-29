from fastapi.testclient import TestClient


def _boot(tmp_path, monkeypatch, token="secret-token"):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    if token is None:
        monkeypatch.delenv("LOVKTV_APP_UPLOAD_TOKEN", raising=False)
    else:
        monkeypatch.setenv("LOVKTV_APP_UPLOAD_TOKEN", token)
    from lovktv import main
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main


def _apk_bytes() -> bytes:
    return b"PK\x03\x04" + b"fake-android-package" * 8


def test_apps_empty_catalog(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        data = client.get("/api/apps").json()
    assert data == {"tv": None, "phone": None}


def test_upload_requires_token(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch, token="secret-token")
    with TestClient(main.app) as client:
        missing = client.post(
            "/api/apps/tv",
            files={
                "file": (
                    "tv.apk",
                    _apk_bytes(),
                    "application/vnd.android.package-archive",
                )
            },
        )
        wrong = client.post(
            "/api/apps/tv",
            files={
                "file": (
                    "tv.apk",
                    _apk_bytes(),
                    "application/vnd.android.package-archive",
                )
            },
            headers={"Authorization": "Bearer other"},
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert "secret-token" not in missing.text
    assert "secret-token" not in wrong.text


def test_upload_disabled_without_env(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch, token=None)
    with TestClient(main.app) as client:
        resp = client.post(
            "/api/apps/phone",
            files={
                "file": (
                    "phone.apk",
                    _apk_bytes(),
                    "application/vnd.android.package-archive",
                )
            },
            headers={"Authorization": "Bearer anything"},
        )
        catalog = client.get("/api/apps").json()
    assert resp.status_code == 503
    assert catalog == {"tv": None, "phone": None}


def test_upload_and_download(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch)
    payload = _apk_bytes()
    with TestClient(main.app) as client:
        uploaded = client.post(
            "/api/apps/tv",
            files={
                "file": (
                    "app-debug.apk",
                    payload,
                    "application/vnd.android.package-archive",
                )
            },
            data={"version": "2026.8.29"},
            headers={"Authorization": "Bearer secret-token"},
        )
        assert uploaded.status_code == 200
        body = uploaded.json()
        assert body["channel"] == "tv"
        assert body["version"] == "2026.8.29"
        assert body["size"] == len(payload)
        assert body["filename"] == "lovktv-tv.apk"
        assert body["url"] == "/apps/tv.apk"
        assert "token" not in body
        catalog = client.get("/api/apps").json()
        assert catalog["tv"]["version"] == "2026.8.29"
        assert catalog["phone"] is None
        direct = client.get("/apps/tv.apk")
        alias = client.get("/api/apps/tv")
    assert direct.status_code == 200
    assert alias.status_code == 200
    assert direct.content == payload
    assert alias.content == payload
    assert "lovktv-tv.apk" in direct.headers.get("content-disposition", "")
    assert (tmp_path / "apps" / "tv.apk").is_file()


def test_reject_unknown_channel_and_garbage(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        unknown = client.post(
            "/api/apps/watch",
            files={
                "file": (
                    "x.apk",
                    _apk_bytes(),
                    "application/vnd.android.package-archive",
                )
            },
            headers={"Authorization": "Bearer secret-token"},
        )
        garbage = client.post(
            "/api/apps/phone",
            files={"file": ("x.bin", b"not-an-apk", "application/octet-stream")},
            headers={"Authorization": "Bearer secret-token"},
        )
        missing = client.get("/apps/phone.apk")
    assert unknown.status_code == 404
    assert garbage.status_code == 400
    assert missing.status_code == 404
