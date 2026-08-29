import re
from pathlib import Path

from fastapi.testclient import TestClient

from lovktv.locale.i18n import LOCALES, locale_keys, parse_lang, translate

FRONTEND = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "public"
    / "shared"
    / "i18n"
    / "locales"
)
_KEY = re.compile(r'"([^"]+)":\s*"')


def _js_keys(lang: str) -> set[str]:
    text = (FRONTEND / f"{lang}.js").read_text(encoding="utf-8")
    return set(_KEY.findall(text))


def test_parse_lang():
    assert parse_lang("yue") == "yue"
    assert parse_lang("zh-HK") == "yue"
    assert parse_lang("zh-MO,zh;q=0.8") == "yue"
    assert parse_lang("ja-JP") == "ja"
    assert parse_lang("en-US,en;q=0.9") == "en"
    assert parse_lang("zh-CN") == "zh"
    assert parse_lang("zh-TW") == "zh"
    assert parse_lang("") == ""
    assert parse_lang("fr") == ""


def test_frontend_locale_keys_match():
    packs = {lang: _js_keys(lang) for lang in LOCALES}
    assert packs["zh"]
    for lang in LOCALES:
        assert packs[lang] == packs["zh"], lang


def test_backend_api_keys_match_frontend():
    front = {key for key in _js_keys("zh") if key.startswith("api.")}
    back = locale_keys("zh")
    assert front == back
    for lang in LOCALES:
        assert locale_keys(lang) == front


def test_translate_interpolation():
    assert "ABC" in translate("zh", "api.search_failed", exc="ABC")
    assert translate("en", "api.song_not_found") == "Song not found"


def test_song_not_found_follows_accept_language(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    with TestClient(main.app) as client:
        zh = client.get("/api/songs/missing")
        en = client.get("/api/songs/missing", headers={"Accept-Language": "en"})
        yue = client.get("/api/songs/missing", headers={"Accept-Language": "zh-HK"})
        ja = client.get("/api/songs/missing", headers={"Accept-Language": "ja"})
        assert zh.status_code == 404
        assert zh.json()["detail"] == "歌曲不存在"
        assert en.json()["detail"] == "Song not found"
        assert yue.json()["detail"] == translate("yue", "api.song_not_found")
        assert ja.json()["detail"] == translate("ja", "api.song_not_found")


def test_learn_prompt_follows_locale():
    from lovktv.workers.learn import build_learn_quiz

    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "走る記憶",
                "zh": "奔跑的记忆",
                "start_ms": 0,
                "end_ms": 1000,
                "tokens": [{"text": "走る", "zh": "奔跑"}],
            }
        ],
    }
    quiz = build_learn_quiz(timeline, {"id": "s1"}, lang="en")
    prompt = quiz["lines"][0]["questions"][0]["prompt"]
    assert prompt in {
        translate("en", "api.learn_meaning"),
        translate("en", "api.learn_word", word="走る"),
    }
