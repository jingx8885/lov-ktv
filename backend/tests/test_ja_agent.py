from lovktv.agents.ja_lyrics import apply_ja_annotation, expand_units, lyric_source_key, _parse_payload
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
