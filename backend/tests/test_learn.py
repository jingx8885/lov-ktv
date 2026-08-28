import json
from pathlib import Path

from fastapi.testclient import TestClient

from lovktv.learn import QUESTIONS_PER_LINE, build_learn_quiz, is_singable_cue


JA_TIMELINE = {
    "language": "ja",
    "cues": [
        {
            "text": "走る記憶",
            "zh": "奔跑的记忆",
            "start_ms": 1000,
            "end_ms": 3200,
            "tokens": [
                {"text": "走る", "zh": "奔跑", "romaji": "hashiru", "start_ms": 1000, "end_ms": 2000},
                {"text": "記憶", "zh": "记忆", "romaji": "kioku", "start_ms": 2000, "end_ms": 3200},
            ],
        },
        {
            "text": "青い空",
            "zh": "蓝色的天空",
            "start_ms": 4000,
            "end_ms": 6200,
            "tokens": [
                {"text": "青い", "zh": "蓝色", "romaji": "aoi", "start_ms": 4000, "end_ms": 5000},
                {"text": "空", "zh": "天空", "romaji": "sora", "start_ms": 5000, "end_ms": 6200},
            ],
        },
        {
            "text": "instrumental",
            "start_ms": 7000,
            "end_ms": 9000,
            "tokens": [],
        },
        {
            "text": "夜の風",
            "zh": "夜里的风",
            "start_ms": 10000,
            "end_ms": 12800,
            "tokens": [
                {"text": "夜", "zh": "夜晚", "romaji": "yoru", "start_ms": 10000, "end_ms": 10800},
                {"text": "の", "zh": "的", "romaji": "no", "start_ms": 10800, "end_ms": 11000},
                {"text": "風", "zh": "风", "romaji": "kaze", "start_ms": 11000, "end_ms": 12800},
            ],
        },
    ],
}


def test_skips_instrumental_and_mixes_meaning_with_words():
    quiz = build_learn_quiz(JA_TIMELINE, {"id": "s1", "title": "群青", "artist": "YOASOBI", "language": "ja"})
    assert quiz["schema"] == "lovktv-learn-v1"
    assert [line["text"] for line in quiz["lines"]] == ["走る記憶", "青い空", "夜の風"]
    first = quiz["lines"][0]
    assert len(first["questions"]) == QUESTIONS_PER_LINE
    kinds = [item["kind"] for item in first["questions"]]
    assert "meaning" in kinds
    assert "word" in kinds
    meaning = next(item for item in first["questions"] if item["kind"] == "meaning")
    assert meaning["prompt"] == "这句是什么意思？"
    assert {choice["text"] for choice in meaning["choices"]} >= {"奔跑的记忆"}
    assert meaning["choices"][meaning["answer"]]["text"] == "奔跑的记忆"
    word = next(item for item in first["questions"] if item["kind"] == "word")
    assert word["stem"] in {"走る", "記憶"}
    assert len(word["choices"]) == 4
    assert quiz["total_questions"] == QUESTIONS_PER_LINE * 3


def test_quiz_is_deterministic():
    song = {"id": "s1", "title": "群青"}
    a = build_learn_quiz(JA_TIMELINE, song)
    b = build_learn_quiz(JA_TIMELINE, song)
    assert a == b


def test_chinese_line_falls_back_to_listen():
    quiz = build_learn_quiz(
        {
            "language": "zh",
            "cues": [
                {"text": "我从草原来", "zh": "我从草原来", "start_ms": 0, "end_ms": 2000, "tokens": []},
                {"text": "千里之外", "zh": "千里之外", "start_ms": 2000, "end_ms": 4000, "tokens": []},
            ],
        },
        {"id": "c1", "language": "zh"},
    )
    kinds = {item["kind"] for line in quiz["lines"] for item in line["questions"]}
    assert kinds == {"listen"}
    first = quiz["lines"][0]["questions"][0]
    assert first["choices"][first["answer"]]["text"] == "我从草原来"


def test_is_singable_cue():
    assert is_singable_cue({"text": "走る"})
    assert not is_singable_cue({"text": "instrumental"})
    assert not is_singable_cue({"text": "♪"})
    assert not is_singable_cue({"text": ""})


def test_phone_learn_shell_is_wired():
    root = Path(__file__).resolve().parents[2] / "frontend" / "public"
    html = (root / "m.html").read_text(encoding="utf-8")
    app = (root / "phone" / "app.js").read_text(encoding="utf-8")
    assert 'id="playerLearnBtn"' in html
    assert 'id="playerLearn"' in html
    assert 'data-learn-mode="quiz"' in html
    assert 'data-learn-mode="echo"' in html
    assert "learn.css" in html
    assert "bindLearn" in app


def test_learn_api_reads_lyrics_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    song = store.create_song("群青", "YOASOBI", "ja")
    store.update_song(song["id"], status="ready")
    folder = store.MEDIA_DIR / song["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "lyrics.json").write_text(json.dumps(JA_TIMELINE, ensure_ascii=False), encoding="utf-8")
    with TestClient(main.app) as client:
        missing = client.get("/api/songs/nope/learn")
        assert missing.status_code == 404
        empty = store.create_song("空", "", "ja")
        store.update_song(empty["id"], status="ready")
        bare = client.get(f"/api/songs/{empty['id']}/learn")
        assert bare.status_code == 409
        res = client.get(f"/api/songs/{song['id']}/learn")
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "群青"
        assert data["modes"] == ["quiz", "echo"]
        assert data["lines"][0]["questions"]
