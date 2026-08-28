from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_entry_html_stays_thin_and_uses_feature_folders():
    phone = (ROOT / "m.html").read_text(encoding="utf-8")
    tv = (ROOT / "tv.html").read_text(encoding="utf-8")
    login = (ROOT / "login.html").read_text(encoding="utf-8")
    assert "function applyKaraokeGain" not in phone
    assert "function hostOrigin" not in tv
    assert "function deviceLogin" not in login
    assert 'href="/phone/shell/css/shell.css' in phone
    assert 'src="/phone/app.js' in phone
    assert 'href="/tv/stage/css/stage.css' in tv
    assert 'src="/tv/app.js' in tv
    assert 'src="/login/js/login.js' in login
    assert (ROOT / "phone" / "player" / "js" / "playback.js").is_file()
    assert (ROOT / "tv" / "auth" / "js" / "login.js").is_file()
    assert (ROOT / "shared" / "audio" / "js" / "aec-worklet.js").is_file()
    assert (ROOT / "landing" / "css" / "landing.css").is_file()


def test_split_assets_are_served(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    with TestClient(main.app) as client:
        for path in (
            "/m.html",
            "/tv.html",
            "/login.html",
            "/phone/app.js",
            "/tv/app.js",
            "/phone/shell/css/shell.css",
            "/tv/stage/css/stage.css",
            "/shared/audio/js/aec.js",
            "/shared/audio/js/aec-worklet.js",
            "/landing/css/landing.css",
        ):
            res = client.get(path)
            assert res.status_code == 200, path
