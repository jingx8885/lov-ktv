from fastapi.testclient import TestClient


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main


def test_host_info_uses_request_origin(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch)
    with TestClient(main.app, base_url="http://192.168.1.8:8787") as client:
        data = client.get("/api/host").json()
    assert data["origin"] == "http://192.168.1.8:8787"
    assert data["process_origin"] == "http://192.168.1.8:8787"
    assert data["mode"] == "server"
    assert data["phone_path"].startswith("/m.html?room=")
    assert data["cache_ready"] == 0
    assert "separator" in data["models"]
    assert "whisper" in data["models"]


def test_tv_page_builds_phone_url_from_host_origin():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[2] / "frontend" / "public" / "tv.html").read_text(encoding="utf-8")
    assert "/api/host" in html
    assert "hostOrigin" in html
    assert "m.html?room=" in html
