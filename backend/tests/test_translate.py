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


def test_apply_zh_keeps_existing_gloss_when_unit_count_differs():
    timeline = {
        "language": "ja",
        "annotation": "ja-agent",
        "cues": [
            {
                "text": "Stay with me まよなかのドアをたたき",
                "source_text": "Stay with me 真夜中のドアをたたき",
                "start_ms": 0,
                "end_ms": 2000,
                "tokens": [
                    {"text": "Stay", "start_ms": 0, "end_ms": 200, "zh": "留在我身边"},
                    {"text": "with", "start_ms": 200, "end_ms": 400},
                    {"text": "me", "start_ms": 400, "end_ms": 600},
                    {
                        "text": "まよなか",
                        "start_ms": 600,
                        "end_ms": 1000,
                        "reading": "真夜中",
                        "zh": "深夜",
                    },
                    {"text": "の", "start_ms": 1000, "end_ms": 1100, "zh": "的"},
                    {
                        "text": "ドア",
                        "start_ms": 1100,
                        "end_ms": 1400,
                        "reading": "door",
                        "zh": "门",
                    },
                    {"text": "を", "start_ms": 1400, "end_ms": 1500, "zh": "把"},
                    {
                        "text": "たたき",
                        "start_ms": 1500,
                        "end_ms": 2000,
                        "reading": "叩",
                        "zh": "敲着",
                    },
                ],
            }
        ],
    }
    apply_zh_translation(
        timeline,
        {
            "lines": [
                {
                    "source": "Stay with me 真夜中のドアをたたき",
                    "zh": "陪着我 敲响午夜的门",
                    "units": [
                        {"sing": "Stay with me", "zh": "陪着我"},
                        {"sing": "真夜中", "zh": "午夜"},
                        {"sing": "の", "zh": "的"},
                        {"sing": "ドア", "zh": "门"},
                        {"sing": "を", "zh": "把"},
                        {"sing": "たたき", "zh": "敲响"},
                    ],
                }
            ],
        },
    )
    cue = timeline["cues"][0]
    assert cue["zh"] == "陪着我 敲响午夜的门"
    assert [tok.get("zh") for tok in cue["tokens"]] == [
        "留在我身边",
        None,
        None,
        "深夜",
        "的",
        "门",
        "把",
        "敲着",
    ]


def test_apply_zh_translation_aligns_grouped_english_units_and_punctuation():
    timeline = {
        "language": "en",
        "cues": [
            {
                "text": "Stay with me, tonight",
                "tokens": [
                    {"text": "Stay"},
                    {"text": "with"},
                    {"text": "me"},
                    {"text": ","},
                    {"text": "tonight"},
                ],
            }
        ],
    }
    apply_zh_translation(
        timeline,
        {
            "lines": [
                {
                    "source": "Stay with me, tonight",
                    "zh": "今晚陪着我",
                    "units": [
                        {"sing": "Stay with me", "zh": "陪着我"},
                        {"sing": "tonight", "zh": "今晚"},
                    ],
                }
            ]
        },
    )
    assert [tok.get("zh") for tok in timeline["cues"][0]["tokens"]] == [
        "陪着我",
        "陪着我",
        "陪着我",
        None,
        "今晚",
    ]


def test_apply_zh_translation_falls_back_for_untranslated_english_function_word():
    timeline = {
        "language": "en",
        "cues": [{"text": "the light", "tokens": [{"text": "the"}, {"text": "light"}]}],
    }
    apply_zh_translation(
        timeline,
        {
            "lines": [
                {
                    "source": "the light",
                    "zh": "这道光",
                    "units": [{"sing": "the", "zh": ""}, {"sing": "light", "zh": "光"}],
                }
            ]
        },
    )
    assert [tok.get("zh") for tok in timeline["cues"][0]["tokens"]] == ["这", "光"]


def test_apply_zh_translation_maps_each_english_word_in_japanese_line():
    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "Give a reason まよなか",
                "tokens": [
                    {"text": "Give"},
                    {"text": "a"},
                    {"text": "reason"},
                    {"text": "まよなか"},
                ],
            }
        ],
    }
    apply_zh_translation(
        timeline,
        {
            "lines": [
                {
                    "source": "Give a reason まよなか",
                    "zh": "给个理由 深夜",
                    "units": [
                        {"sing": "Give", "zh": "给"},
                        {"sing": "a", "zh": "一个"},
                        {"sing": "reason", "zh": "理由"},
                        {"sing": "まよなか", "zh": "深夜"},
                    ],
                }
            ]
        },
    )
    assert [tok.get("zh") for tok in timeline["cues"][0]["tokens"]] == [
        "给",
        "一个",
        "理由",
        "深夜",
    ]


def test_set_mix_stores_lyric_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import room_store, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    room_store.ensure_room("LYR1")
    snap = room_store.set_mix("LYR1", lyric_mode="roma")
    assert snap["lyric_mode"] == "roma"
    snap = room_store.set_mix("LYR1", lyric_mode="nope")
    assert snap["lyric_mode"] == "all"
