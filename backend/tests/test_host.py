from fastapi.testclient import TestClient


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main


def test_host_info_uses_request_origin(tmp_path, monkeypatch):
    monkeypatch.delenv("LOVKTV_AGENT_URL", raising=False)
    monkeypatch.delenv("LOVKTV_AGENT_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    main = _boot(tmp_path, monkeypatch)
    with TestClient(main.app, base_url="http://192.168.1.8:8787") as client:
        data = client.get("/api/host").json()
    assert data["origin"] == "http://192.168.1.8:8787"
    assert data["process_origin"] == "http://192.168.1.8:8787"
    assert data["mode"] == "server"
    assert data["phone_path"].startswith("/m.html?room=")
    assert data["cache_ready"] == 0
    assert data["mic_port"] == 0
    assert data["mic_sample_rate"] == 48000
    assert "separator" in data["models"]
    assert "whisper" in data["models"]
    assert data["agent"]["enabled"] is False
    assert data["agent"]["model"] == ""


def test_phone_player_avoids_hard_seek_on_original():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[2] / "frontend" / "public" / "m.html").read_text(encoding="utf-8")
    assert 'id="playerOriginal" preload="auto"' in html
    assert "function mediaAhead" in html
    assert "orig.seeking" in html
    assert "0.32" in html
    assert "playerOrigWait" in html
    sync = html.split("function syncOriginal", 1)[1].split("function applyPlayerVocalMix", 1)[0]
    assert "orig.currentTime = clock" in sync
    assert "targetReady" in sync
    assert "> 0.08" not in sync


def test_tv_page_builds_phone_url_from_host_origin():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[2] / "frontend" / "public" / "tv.html").read_text(encoding="utf-8")
    assert "/api/host" in html
    assert "hostOrigin" in html
    assert "m.html?room=" in html
