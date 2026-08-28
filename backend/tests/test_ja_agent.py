from lovktv.agents.ja_lyrics import (
    apply_ja_annotation,
    expand_units,
    japanese_from_units,
    line_is_romaji,
    lyric_source_key,
    _parse_payload,
)
from lovktv.pipeline.lyrics import ja_token_specs, tokenize


def test_parse_payload_accepts_fenced_json():
    raw = """```json
{"lines":[{"source":"溢れるメモリー","units":[{"sing":"あふれる","label":"溢"},{"sing":"メモリー","label":"memory"}]}]}
```"""
    notes = _parse_payload(raw)
    assert notes["lines"][0]["units"][1]["label"] == "memory"


def test_expand_strips_okurigana_and_splits_leftover_kanji():
    specs = expand_units(
        [
            {"sing": "どうでもいいような夜だけど", "label": ""},
            {"sing": "とまった", "label": "止まった"},
        ]
    )
    sung = "".join(piece for piece, _label in specs)
    assert "夜" not in sung
    assert ("よる", "夜") in specs
    assert ("とまった", "止") in specs


def test_expand_splits_multi_kanji_okurigana():
    specs = expand_units([{"sing": "はしりつづける", "label": "走り続ける"}])
    assert specs == [("はしり", "走"), ("つづけ", "続"), ("る", "")]


def test_expand_keeps_etymology_kanji_on_sung_kana():
    assert expand_units([{"sing": "もがいてる", "label": "藻掻", "romaji": "mogaiteru"}]) == [
        ("もがいてる", "藻掻")
    ]


def test_expand_merges_okurigana_leftover_after_compound():
    specs = expand_units(
        [{"sing": "だいじにしていた", "label": "大事にしていた", "romaji": "daiji ni shite ita"}],
        source="まだ忘れず 大事にしていた",
    )
    assert specs[0] == ("だいじ", "大事")
    assert specs[1] == ("にしていた", "")
    assert "に" not in [piece for piece, _label in specs]


def test_expand_keeps_katakana_as_one_token():
    specs = expand_units(
        [
            {"sing": "あふれる", "label": "溢"},
            {"sing": "メモリー", "label": "memory"},
            {"sing": "ズレ", "label": ""},
        ]
    )
    assert ("メモリー", "memory") in specs
    assert ("ズレ", "") in specs
    assert specs[0] == ("あふれる", "溢")
    assert expand_units([{"sing": "ひびき", "label": "響"}]) == [("ひびき", "響")]


def test_latin_words_stay_whole_in_japanese_line():
    specs = ja_token_specs("未来の自分へと Give a reason for life 届けたい")
    sung = [piece for piece, _label in specs]
    assert "Give" in sung
    assert "reason" in sung
    assert "G" not in sung
    assert tokenize("Here we go! go! 走り続ける", "ja")[:4] == ["Here", "we", "go!", "go!"]


def test_expand_strips_numbered_sing_and_splits_compound_kanji():
    specs = expand_units(
        [
            {"sing": "1. It's only love", "label": ""},
            {"sing": "4. もしも", "label": ""},
        ]
    )
    sung = [piece for piece, _label in specs]
    assert "1." not in sung
    assert "4." not in sung
    assert sung[:3] == ["It's", "only", "love"]
    assert sung[3:] == ["も", "し", "も"]

    compound = expand_units(
        [{"sing": "しらずしらず", "label": "知知"}],
        source="知らず知らず隠してた",
    )
    assert ("しらず", "知") in compound
    assert [label for _piece, label in compound].count("知") == 2


def test_expand_keeps_english_words_and_skips_line_numbers():
    specs = expand_units(
        [
            {"sing": "14.", "label": ""},
            {"sing": "Here we go!", "label": ""},
            {"sing": "はしりつづける", "label": "走り続ける"},
        ]
    )
    sung = [piece for piece, _label in specs]
    assert "14." not in sung
    assert sung[:3] == ["Here", "we", "go!"]
    assert ("はしり", "走") in specs
    assert ("つづけ", "続") in specs


def test_apply_matches_numbered_agent_source():
    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "Here we go! go! 走り続ける",
                "start_ms": 1000,
                "end_ms": 2000,
                "tokens": [{"text": "H", "start_ms": 1000, "end_ms": 2000, "reading": ""}],
            }
        ],
    }
    apply_ja_annotation(
        timeline,
        {
            "model": "test-agent",
            "lines": [
                {
                    "source": "14. Here we go! go! 走り続ける",
                    "units": [
                        {"sing": "14.", "label": ""},
                        {"sing": "Here", "label": ""},
                        {"sing": "we", "label": ""},
                        {"sing": "go!", "label": ""},
                        {"sing": "go!", "label": ""},
                        {"sing": "はしりつづける", "label": "走り続ける"},
                    ],
                }
            ],
        },
    )
    texts = [tok["text"] for tok in timeline["cues"][0]["tokens"]]
    assert texts[:4] == ["Here", "we", "go!", "go!"]
    assert "H" not in texts
    assert ("はしり", "走") in [(tok["text"], tok["reading"]) for tok in timeline["cues"][0]["tokens"]]
    assert lyric_source_key("14. Here we go! go! 走り続ける") == "Here we go! go! 走り続ける"


def test_apply_annotation_replaces_tokens_and_keeps_line_time():
    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "溢れるメモリー",
                "start_ms": 1000,
                "end_ms": 3000,
                "tokens": [{"text": "溢", "start_ms": 1000, "end_ms": 3000, "reading": ""}],
            }
        ],
    }
    apply_ja_annotation(
        timeline,
        {
            "model": "test-agent",
            "lines": [
                {
                    "source": "溢れるメモリー",
                    "units": [
                        {"sing": "あふれる", "label": "溢"},
                        {"sing": "メモリー", "label": "memory"},
                    ],
                }
            ],
        },
    )
    tokens = timeline["cues"][0]["tokens"]
    assert "".join(tok["text"] for tok in tokens) == "あふれるメモリー"
    assert any(tok["reading"] == "memory" for tok in tokens)
    assert tokens[0]["start_ms"] == 1000
    assert tokens[-1]["end_ms"] == 3000
    assert timeline["annotation"] == "ja-agent"


def test_apply_annotation_uses_sing_end_not_hold():
    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "溢れるメモリー",
                "start_ms": 1000,
                "end_ms": 5000,
                "sing_end_ms": 2200,
                "tokens": [{"text": "溢", "start_ms": 1000, "end_ms": 5000, "reading": ""}],
            }
        ],
    }
    apply_ja_annotation(
        timeline,
        {
            "model": "test-agent",
            "lines": [
                {
                    "source": "溢れるメモリー",
                    "units": [
                        {"sing": "あふれる", "label": "溢"},
                        {"sing": "メモリー", "label": "memory"},
                    ],
                }
            ],
        },
    )
    tokens = timeline["cues"][0]["tokens"]
    assert tokens[0]["start_ms"] == 1000
    assert tokens[-1]["end_ms"] == 2200
    assert timeline["cues"][0]["end_ms"] == 5000


def test_romaji_line_becomes_japanese_with_labels():
    assert line_is_romaji("aa, itsumo no you ni")
    assert not line_is_romaji("いつものように")
    assert not line_is_romaji("Here we go! 走り続ける")
    assert japanese_from_units(
        [{"sing": "いつもの"}, {"sing": "ように"}]
    ) == "いつものように"
    assert japanese_from_units(
        [{"sing": "Give"}, {"sing": "a"}, {"sing": "reason"}]
    ) == "Give a reason"

    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "aa, itsumo no you ni",
                "start_ms": 1000,
                "end_ms": 3000,
                "tokens": [{"text": "aa", "start_ms": 1000, "end_ms": 3000, "reading": ""}],
            }
        ],
    }
    apply_ja_annotation(
        timeline,
        {
            "model": "test-agent",
            "lines": [
                {
                    "source": "aa, itsumo no you ni",
                    "units": [
                        {"sing": "ああ、", "label": "", "romaji": "aa"},
                        {"sing": "いつもの", "label": "", "romaji": "itsumo no"},
                        {"sing": "ように", "label": "", "romaji": "you ni"},
                    ],
                }
            ],
        },
    )
    cue = timeline["cues"][0]
    assert cue["source_text"] == "aa, itsumo no you ni"
    assert cue["text"] == "ああ、いつものように"
    texts = [(tok["text"], tok["reading"], tok["romaji"]) for tok in cue["tokens"]]
    assert ("いつもの", "", "itsumo no") in texts
    assert ("ように", "", "you ni") in texts
    assert expand_units([{"sing": "いつもの", "label": "", "romaji": "itsumo no"}]) == [
        ("いつもの", "")
    ]


def test_apply_keeps_kanji_line_and_rematch_source_text():
    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "溢れるメモリー",
                "start_ms": 1000,
                "end_ms": 2000,
                "tokens": [],
            }
        ],
    }
    notes = {
        "model": "test-agent",
        "lines": [
            {
                "source": "溢れるメモリー",
                "units": [
                    {"sing": "あふれる", "label": "溢", "romaji": "afureru"},
                    {"sing": "メモリー", "label": "memory", "romaji": ""},
                ],
            }
        ],
    }
    apply_ja_annotation(timeline, notes)
    assert timeline["cues"][0]["text"] == "溢れるメモリー"
    assert timeline["cues"][0]["tokens"][0]["romaji"] == "afureru"
    assert timeline["cues"][0]["tokens"][1]["reading"] == "memory"

    timeline["cues"][0]["source_text"] = "aa, itsumo no you ni"
    timeline["cues"][0]["text"] = "ああ、いつものように"
    apply_ja_annotation(
        timeline,
        {
            "model": "test-agent",
            "lines": [
                {
                    "source": "aa, itsumo no you ni",
                    "units": [
                        {"sing": "ああ、", "label": "", "romaji": "aa"},
                        {"sing": "きみ", "label": "君", "romaji": "kimi"},
                    ],
                }
            ],
        },
    )
    assert timeline["cues"][0]["text"] == "ああ、きみ"
    assert ("きみ", "君", "kimi") in [
        (tok["text"], tok["reading"], tok["romaji"]) for tok in timeline["cues"][0]["tokens"]
    ]


def test_parse_payload_keeps_romaji():
    notes = _parse_payload(
        '{"lines":[{"source":"kimi","units":[{"sing":"きみ","label":"君","romaji":"kimi"}]}]}'
    )
    assert notes["lines"][0]["units"][0]["romaji"] == "kimi"


def test_apply_annotation_keeps_line_and_word_zh():
    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "溢れるメモリー",
                "start_ms": 0,
                "end_ms": 1000,
                "tokens": [],
            }
        ],
    }
    apply_ja_annotation(
        timeline,
        {
            "lines": [
                {
                    "source": "溢れるメモリー",
                    "zh": "满溢的记忆",
                    "units": [
                        {"sing": "あふれる", "label": "溢", "romaji": "afureru", "zh": "满溢"},
                        {"sing": "メモリー", "label": "memory", "zh": "记忆"},
                    ],
                }
            ],
        },
    )
    cue = timeline["cues"][0]
    assert cue["zh"] == "满溢的记忆"
    assert [tok.get("zh") for tok in cue["tokens"]] == ["满溢", "记忆"]


def test_apply_skips_truncated_romaji_restore():
    timeline = {
        "language": "ja",
        "cues": [
            {
                "text": "me magurushii jikan no mure ga",
                "source_text": "me magurushii jikan no mure ga",
                "start_ms": 0,
                "end_ms": 1000,
                "tokens": [{"text": "me", "start_ms": 0, "end_ms": 1000, "reading": ""}],
            }
        ],
    }
    apply_ja_annotation(
        timeline,
        {
            "lines": [
                {
                    "source": "me magurushii jikan no mure ga",
                    "zh": "纷乱的时间群涌而来",
                    "units": [
                        {"sing": "め", "label": "", "romaji": "me", "zh": "我"},
                        {"sing": "まぐるしい", "label": "", "romaji": "magurushii", "zh": "纷乱"},
                    ],
                }
            ],
        },
    )
    cue = timeline["cues"][0]
    assert cue["text"] == "me magurushii jikan no mure ga"
    assert cue["tokens"][0]["text"] == "me"


def test_needs_romaji_restore():
    from lovktv.restore_ja import already_restored, needs_romaji_restore

    assert needs_romaji_restore({"language": "ja", "cues": [{"text": "aa, itsumo"}]})
    assert already_restored(
        {"language": "ja", "cues": [{"text": "いつもの", "source_text": "itsumo no"}]}
    )
    assert not needs_romaji_restore(
        {"language": "ja", "cues": [{"text": "いつもの", "source_text": "itsumo no"}]}
    )
    assert not needs_romaji_restore({"language": "en", "cues": [{"text": "hello"}]})
    assert not needs_romaji_restore({"language": "ja", "cues": [{"text": "いつものように"}]})
