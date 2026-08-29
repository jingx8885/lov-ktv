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
    assert QUESTIONS_PER_LINE == 1
    assert len(first["questions"]) == 1
    item = first["questions"][0]
    assert item["kind"] in {"meaning", "word"}
    assert len(item["choices"]) == 4
    if item["kind"] == "meaning":
        assert item["prompt"] == "这句是什么意思？"
        assert item["choices"][item["answer"]]["text"] == "奔跑的记忆"
    else:
        assert item["stem"] in {"走る", "記憶", "夜", "の", "風", "青い", "空"}
        assert item["choices"][item["answer"]]["text"]
    assert quiz["total_questions"] == 3
    assert [item["text"] for item in first["words"]] == ["走る", "記憶"]
    night = next(line for line in quiz["lines"] if line["text"] == "夜の風")
    assert [item["text"] for item in night["words"]] == ["夜", "の", "風"]


def test_tap_words_keeps_order_and_skips_punct():
    from lovktv.learn import tap_words

    words = tap_words(
        {
            "text": "夜の、風の音",
            "tokens": [
                {"text": "夜", "zh": "夜晚", "romaji": "yoru"},
                {"text": "の", "zh": "的", "romaji": "no"},
                {"text": "、"},
                {"text": "風", "zh": "风", "romaji": "kaze"},
                {"text": "の", "zh": "的", "romaji": "no"},
                {"text": "音", "zh": "声音", "romaji": "oto"},
            ],
        }
    )
    assert [item["text"] for item in words] == ["夜", "の", "風", "の", "音"]
    assert words[1]["romaji"] == "no"
    assert words[3]["romaji"] == "no"
    latin = tap_words({"text": "hello world", "tokens": []})
    assert [item["text"] for item in latin] == ["hello", "world"]
    chars = tap_words({"text": "我从草原来", "tokens": []})
    assert [item["text"] for item in chars] == list("我从草原来")


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
    transport = html.split('class="player-transport"', 1)[1].split("</div>", 1)[0]
    assert 'id="playerLearnBtn"' in transport
    assert transport.index('id="playerPlay"') < transport.index('id="playerLearnBtn"')
    assert 'id="tabLearn"' in html
    assert "data-enter-learn" in html
    assert 'id="playerLearn"' in html
    assert 'data-learn-mode="quiz"' in html
    assert 'data-learn-mode="tap"' in html
    assert 'data-learn-mode="echo"' in html
    assert 'id="learnTap"' in html
    assert 'id="learnTapFx"' in html
    assert "stage-fx.js" in html
    assert "learn.css" in html
    assert "learn-quiz.css" in html
    assert "learn-tap.css" in html
    assert "learn-echo.css" in html
    assert "bindLearn" in app
    assert 'id="learnFx"' in html
    shell = (root / "phone" / "player" / "js" / "learn.js").read_text(encoding="utf-8")
    css = (root / "phone" / "player" / "css" / "learn.css").read_text(encoding="utf-8")
    quiz = (root / "phone" / "player" / "js" / "learn-quiz.js").read_text(encoding="utf-8")
    tap = (root / "phone" / "player" / "js" / "learn-tap.js").read_text(encoding="utf-8")
    echo = (root / "phone" / "player" / "js" / "learn-echo.js").read_text(encoding="utf-8")
    fx = (root / "phone" / "player" / "js" / "learn-fx.js").read_text(encoding="utf-8")
    assert ".learn-body[hidden]" in css
    assert "learnTapGo" not in shell
    assert "learnTapGo" not in html
    assert "learnQuizGo" not in html
    assert "learnEchoGo" not in html
    assert 'id="learnQuizNext"' in html
    assert 'id="learnTapNext"' in html
    assert "learnQuizNext" in quiz
    assert "learnTapNext" in tap
    assert "confirmLineHold" in quiz
    assert "holdAfterLine" not in echo
    assert 'id="learnCount"' in html
    assert 'id="learnLyricMode"' in html
    assert 'id="learnQuizPrompt"' in html
    assert 'id="learnTapSrc"' in html
    assert 'id="learnTapRoma"' in html
    assert "data-learn-diff" in html
    assert "runCountdown" in fx
    assert "kickPlayerPaint" in shell
    paint = (root / "shared" / "lyrics" / "js" / "paint.js").read_text(encoding="utf-8")
    assert "clusterTokens" in paint
    assert "isKanjiText(reading)" in paint
    assert "fitLyricExtras" in paint
    assert "fitLyricLine" in paint
    assert "function tvStage()" in paint
    assert "if (tvStage()) return;" in paint
    assert 'fitKey = `${id}:${Math.round(el.clientWidth)}`' in paint
    assert "el.clientHeight" not in paint
    assert "line-words" in paint
    assert "kickPlayerPaint" in (root / "phone" / "player" / "js" / "lyrics.js").read_text(encoding="utf-8")
    play = (root / "phone" / "player" / "js" / "learn-play.js").read_text(encoding="utf-8")
    assert "setLearnDiff" in play
    assert "playbackRate" in play
    assert "export function paintLearnLine" in play
    assert 'hold: "confirm"' in play
    assert "hold: 5000" in play
    assert "rate: 1.25" not in play
    assert "export function holdAfterLine" in play
    assert "needsLineHold" in quiz
    assert "needsLineHold" in tap
    assert "holdAfterLine" in quiz
    assert "holdAfterLine" in tap
    rtc = (root / "phone" / "room" / "js" / "rtc.js").read_text(encoding="utf-8")
    assert "LovKtvNative" in rtc
    assert "usesNativeMic" in rtc
    assert "phone.mic.needTv" in rtc
    assert "paintLearnLine" in quiz
    assert "item.prompt" in quiz
    assert "paintLearnLine" in tap
    assert "learnTapSrc" in tap
    assert "paintLearnLine" in echo
    assert "learnEchoGo" not in shell
    assert "bindQuiz" in quiz
    assert "lineAt" in quiz
    assert "cancelCueWindow" in quiz
    assert "bindTap" in tap
    assert "lineAt" in tap
    assert "scatterTiles" in tap
    assert "TILE_SKINS" in tap
    assert "LovStageFx" in tap
    assert "--tile-bg" in tap
    assert "bindEcho" in echo
    assert "export function singWindowEnd" in echo
    assert "SING_MIN_MS" in echo
    assert "learnEchoPreview" in echo
    assert "learnEchoRetry" in echo
    assert "learnEchoNext" in echo
    assert 'id="learnEchoPreview"' in html
    assert 'id="learnEchoRetry"' in html
    assert 'id="learnEchoNext"' in html
    zh = (root / "shared" / "i18n" / "locales" / "zh.js").read_text(encoding="utf-8")
    assert '"phone.player.learn": "游戏"' in zh
    assert '"learn.title": "游戏"' in zh
    assert '"learn.next": "下一句"' in zh
    assert '"learn.holdWait"' in zh
    assert '"phone.mic.opened"' in zh
    assert '"learn.echo": "翻唱挑战"' in zh
    assert "celebrateCorrect" in quiz
    assert "SFX_GAIN = 0.068" in fx
    assert "pausePlayer" not in fx
    assert "applyKaraokeGain" not in fx
    assert "bus.connect(ctx.destination)" in fx


def test_learn_api_reads_lyrics_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    main.MEDIA_DIR = store.MEDIA_DIR
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
        assert data["modes"] == ["quiz", "tap", "echo"]
        assert data["lines"][0]["questions"]
        assert [item["text"] for item in data["lines"][0]["words"]] == ["走る", "記憶"]
