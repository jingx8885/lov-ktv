from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_runtime_directories_have_one_taxonomy_level():
    expected = {
        ROOT / "phone" / "player" / "js": {"learn", "playback"},
        ROOT / "phone" / "room" / "js": {"room"},
        ROOT / "shared" / "audio" / "js": {"aec", "bands", "rtc"},
        ROOT / "tv" / "playback" / "js": {"lyric", "media", "remote", "room", "runtime"},
    }
    for folder, names in expected.items():
        assert not [path for path in folder.iterdir() if path.is_file()], folder
        assert {path.name for path in folder.iterdir() if path.is_dir()} == names

    phone_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "phone").rglob("*.js")
    )
    shared_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "shared").rglob("*.js")
    )
    assert "/tv/" not in phone_sources
    assert "/phone/" not in shared_sources
    assert "/tv/" not in shared_sources
    assert not (ROOT / "tv" / "fx").exists()
    assert not (ROOT / "phone" / "room" / "js" / "native").exists()


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
    http = (ROOT / "shared" / "ui" / "js" / "http.js").read_text(encoding="utf-8")
    join = (ROOT / "phone" / "room" / "js" / "room" / "join.js").read_text(encoding="utf-8")
    assert "X-LovKtv-Machine" in http
    assert "LovKtvPlatform.http" in http
    assert 'fetchJson(roomUrl("/api/rooms"))' in join
    assert 'src="/login/js/login.js' in login
    for module in (
        "media.js",
        "controls.js",
        "queue.js",
        "lyrics.js",
        "song.js",
        "ui.js",
    ):
        assert (ROOT / "phone" / "player" / "js" / "playback" / module).is_file()
    assert (ROOT / "phone" / "player" / "js" / "learn" / "index.js").is_file()
    assert (ROOT / "phone" / "player" / "css" / "learn.css").is_file()
    assert (ROOT / "tv" / "auth" / "js" / "login.js").is_file()
    assert (ROOT / "shared" / "audio" / "js" / "aec" / "worklet.js").is_file()
    assert (ROOT / "landing" / "css" / "landing.css").is_file()
    assert (ROOT / "brand" / "logo.svg").is_file()
    assert (ROOT / "brand" / "icon.png").is_file()
    mic = phone.split('id="playerMic"', 1)[1].split("</button>", 1)[0]
    vocal = phone.split('id="playerVocal"', 1)[1].split("</button>", 1)[0]
    iem = phone.split('id="playerIem"', 1)[1].split("</button>", 1)[0]
    assert "<svg" in mic and "<svg" in vocal and "<svg" in iem
    assert mic[mic.index("<svg") :] != vocal[vocal.index("<svg") :]
    assert vocal[vocal.index("<svg") :] != iem[iem.index("<svg") :]


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
            "/phone/install.js",
            "/tv/app.js",
            "/tv/install.js",
            "/shared/ui/js/http.js",
            "/shared/i18n/js/i18n.js",
            "/shared/i18n/locales/zh.js",
            "/shared/i18n/locales/yue.js",
            "/shared/i18n/locales/en.js",
            "/shared/i18n/locales/ja.js",
            "/phone/shell/css/shell.css",
            "/phone/player/css/learn.css",
            "/phone/player/css/learn-quiz.css",
            "/phone/player/css/learn-tap.css",
            "/phone/player/css/learn-echo.css",
            "/phone/player/js/learn/index.js",
            "/phone/player/js/learn/fx.js",
            "/phone/player/js/learn/tap.js",
            "/shared/fx/js/stage/primitives.js",
            "/shared/fx/js/stage/build.js",
            "/shared/fx/js/stage/draw.js",
            "/shared/fx/js/stage/runtime.js",
            "/shared/fx/js/stage/party.js",
            "/shared/fx/js/stage/hooks.js",
            "/tv/stage/css/stage.css",
            "/shared/audio/js/aec/index.js",
            "/shared/audio/js/aec/worklet.js",
            "/landing/css/landing.css",
            "/brand/logo.svg",
            "/brand/icon.png",
            "/brand/apple-touch.png",
            "/brand/splash-tv.jpg",
            "/brand/splash-phone.jpg",
            "/brand/wait-tv.jpg",
        ):
            res = client.get(path)
            assert res.status_code == 200, path
