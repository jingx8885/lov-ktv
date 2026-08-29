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
    assert data["database"] == "sqlite"
    assert data["agent"]["enabled"] is False
    assert data["agent"]["model"] == ""


def test_phone_player_overlays_guide_on_karaoke():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "frontend" / "public"
    html = (root / "m.html").read_text(encoding="utf-8")
    player = (root / "phone" / "player" / "js" / "playback.js").read_text(encoding="utf-8")
    assert 'id="playerGuide" preload="auto"' in html
    assert 'id="playerOriginal"' not in html
    assert "function syncOriginal" not in player
    assert "orig.src = original" not in player
    gain = player.split("function applyKaraokeGain", 1)[1].split("function syncGuide", 1)[0]
    assert "playerVocal" not in gain
    assert "value = editing && !state.mixTrackOn ? 0 : 1" in gain
    sync = player.split("function syncGuide", 1)[1].split("function applyPlayerVocalMix", 1)[0]
    assert 'mediaUrl(song.id, "guide.m4a")' in player
    assert "0.32" in sync
    assert "playerVocal" in sync
    assert "function mediaAhead" in player


def test_phone_player_starts_when_song_clicked():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "frontend" / "public"
    player = (root / "phone" / "player" / "js" / "playback.js").read_text(encoding="utf-8")
    nav = (root / "phone" / "nav" / "js" / "pages.js").read_text(encoding="utf-8")
    assert "unlockPlayerGesture" in player
    assert 'loadPlayerSong(btn.dataset.pick, { play: true })' in player
    assert 'loadPlayerSong(songId, { play: true })' in nav
    assert 'play: !$("playerAudio").paused' not in player
    assert 'play: !$("playerAudio").paused' not in nav


def test_tv_page_builds_phone_url_from_host_origin():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "frontend" / "public" / "tv"
    login = (root / "auth" / "js" / "login.js").read_text(encoding="utf-8")
    app = (root / "app.js").read_text(encoding="utf-8")
    assert "/api/host" in login
    assert "hostOrigin" in login
    assert "m.html?room=" in login
    assert "state.room = roomRes.data" in login
    assert "data.phone_url" in login
    assert "&process=" in login
    assert 'qr.querySelector("canvas, img, svg")' in app
    assert "data.phone_url" in login
    assert "lastPhoneUrl" in login
