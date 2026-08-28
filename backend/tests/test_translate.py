from lovktv.agents.translate import apply_zh_translation, is_chinese_lang


def test_is_chinese_lang():
    assert is_chinese_lang("zh")
    assert is_chinese_lang("zh-CN")
    assert not is_chinese_lang("ja")
    assert not is_chinese_lang("en")


def test_apply_zh_translation_fills_line_and_tokens():
    timeline = {
        "language": "en",
        "cues": [
            {
                "text": "in the end",
                "start_ms": 0,
                "end_ms": 1200,
                "tokens": [
                    {"text": "in", "start_ms": 0, "end_ms": 300},
                    {"text": "the", "start_ms": 300, "end_ms": 500},
                    {"text": "end", "start_ms": 500, "end_ms": 1200},
                ],
            }
        ],
    }
    apply_zh_translation(
        timeline,
        {
            "model": "test",
            "lines": [
                {
                    "source": "in the end",
                    "zh": "到最后",
                    "units": [
                        {"sing": "in", "zh": "在"},
                        {"sing": "the", "zh": "这"},
                        {"sing": "end", "zh": "终点"},
                    ],
                }
            ],
        },
    )
    cue = timeline["cues"][0]
    assert cue["zh"] == "到最后"
    assert [tok["zh"] for tok in cue["tokens"]] == ["在", "这", "终点"]
    assert timeline["translation"] == "lovjpn-zh"


def test_set_mix_stores_lyric_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    store.ensure_room("LYR1")
    snap = store.set_mix("LYR1", lyric_mode="roma")
    assert snap["lyric_mode"] == "roma"
    snap = store.set_mix("LYR1", lyric_mode="nope")
    assert snap["lyric_mode"] == "all"
