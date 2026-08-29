from lovktv.catalog.fetch import is_clean_title, parse_lrc
from lovktv.pipeline.language import detect_language
from lovktv.pipeline.lyrics import (
    drop_credit_lines,
    drop_leading_title_echo,
    drop_translation_lines,
    fold_ja_netease_kanji,
    is_credit_lyric,
    timeline_from_lrc,
    tokenize,
)


def test_parse_lrc_skips_meta_and_dedups():
    lrc = """
[00:00.00]作词 : テスト
[00:12.10]過ぎる日々にあくびが出る
[00:12.20]過ぎる日々にあくびが出る
[00:16.00]本当の自分に出会えた
"""
    lines = parse_lrc(lrc)
    assert [item["text"] for item in lines] == [
        "過ぎる日々にあくびが出る",
        "本当の自分に出会えた",
    ]
    assert lines[0]["ms"] == 12100


def test_empty_timestamp_closes_previous_line():
    lines = parse_lrc(
        """
[00:01.05]どうでもいいような夜だけど
[00:04.71]響き煌めきと君も
[00:09.18]
[00:25.06]まだ止まった刻む針も
"""
    )
    assert [item["text"] for item in lines] == [
        "どうでもいいような夜だけど",
        "響き煌めきと君も",
        "まだ止まった刻む針も",
    ]
    assert lines[1]["end_ms"] == 9180
    assert "end_ms" not in lines[2]


def test_netease_end_stamp_closes_earlier_line():
    lines = parse_lrc(
        """
[00:24.882]これでいい
[00:25.865]知らず知らず隠してた
[00:25.565]
[00:28.599]本当の声を響かせてよほら
[04:07.390]-
"""
    )
    assert [item["text"] for item in lines] == [
        "これでいい",
        "知らず知らず隠してた",
        "本当の声を響かせてよほら",
    ]
    assert lines[0]["end_ms"] == 25565
    assert "end_ms" not in lines[1]


def test_reject_karaoke_titles():
    assert is_clean_title("群青")
    assert not is_clean_title("群青 カラオケ")
    assert not is_clean_title("Lemon off vocal")
    assert not is_clean_title("晴天 (cover)")


def test_drop_chinese_gloss_from_japanese_lrc():
    lines = parse_lrc(
        """
[00:00.00]It's only love
[00:10.19]这 是仅有的爱
[00:18.80]もしも 願い 一つだけ
[00:23.66]如果只有一个愿望
[00:37.17]Beautiful world
"""
    )
    kept = drop_leading_title_echo(drop_translation_lines(lines, "ja"))
    assert [item["text"] for item in kept] == [
        "It's only love",
        "もしも 願い 一つだけ",
        "Beautiful world",
    ]
    leftover = drop_translation_lines(
        [{"ms": 167190, "text": "就 当做积攒一些经验"}, {"ms": 169100, "text": "新聞なんかいらない"}],
        "ja",
    )
    assert [item["text"] for item in leftover] == ["新聞なんかいらない"]
    echoed = drop_leading_title_echo(
        [
            {"ms": 0, "text": "It's only love"},
            {"ms": 13600, "text": "It's only love"},
            {"ms": 18800, "text": "もしも"},
        ]
    )
    assert [item["ms"] for item in echoed] == [13600, 18800]


def test_language_and_tokens():
    assert detect_language("過ぎる日々にあくびが出る") == "ja"
    assert detect_language("我听见下雨的声音") == "zh"
    assert detect_language("I see you") == "en"
    assert detect_language("立ち向かう先に乾いた風", "zh") == "ja"
    assert detect_language("It's only love", "zh") == "en"
    assert tokenize("晴天", "zh") == ["晴", "天"]
    assert tokenize("I see", "en") == ["I", "see"]
    assert tokenize("I close my eyes and I can see", "zh") == [
        "I",
        "close",
        "my",
        "eyes",
        "and",
        "I",
        "can",
        "see",
    ]


def test_timeline_char_then_word():
    ja = timeline_from_lrc(
        [{"ms": 0, "text": "こんにちは"}, {"ms": 1000, "text": "世界"}],
        "ja",
    )
    assert ja["language"] == "ja"
    assert [tok["text"] for tok in ja["cues"][0]["tokens"]] == list("こんにちは")
    assert ja["cues"][0]["tokens"][0]["start_ms"] == 0
    assert ja["cues"][0]["tokens"][-1]["end_ms"] == 1000
    world = ja["cues"][1]["tokens"]
    assert "".join(tok["text"] for tok in world) == "".join(tokenize("世界", "ja"))
    assert world[0]["text"] == "世界"
    assert world[0]["reading"] == "せかい"

    en = timeline_from_lrc(
        [{"ms": 0, "text": "hello world"}, {"ms": 2000, "text": "again"}],
        "en",
    )
    assert [tok["text"] for tok in en["cues"][0]["tokens"]] == ["hello", "world"]


def test_netease_ja_credits_and_simplified_kanji():
    assert fold_ja_netease_kanji("目まぐるしい 时间の群れが") == "目まぐるしい 時間の群れが"
    assert fold_ja_netease_kanji("谁にも止められはしない") == "誰にも止められはしない"
    assert is_credit_lyric("「Give a reason」")
    assert is_credit_lyric("「スレイヤーズNEXT」OP")
    assert is_credit_lyric("発売日：1996/04/24")
    assert not is_credit_lyric("Here we go! go! 走り続ける")
    cleaned = drop_credit_lines(
        [
            {"ms": 0, "text": "「Give a reason」"},
            {"ms": 6000, "text": "「スレイヤーズNEXT」OP"},
            {"ms": 33750, "text": "目まぐるしい 时间の群れが"},
            {"ms": 246000, "text": "発売日：1996/04/24"},
        ],
        "ja",
    )
    assert [item["text"] for item in cleaned] == ["目まぐるしい 時間の群れが"]


def test_ja_compatibility_kanji_is_normalized():
    from lovktv.pipeline.lyrics import build_cue

    cue = build_cue("響めき", 0, 1000, "ja")
    sung = "".join(tok["text"] for tok in cue["tokens"])
    assert "響" not in sung
    assert "響" in sung
    assert any("\u3040" <= char <= "\u309f" for tok in cue["tokens"] for char in tok["reading"])


def test_ja_kanji_shows_kanji_with_hiragana_above():
    from lovktv.pipeline.lyrics import build_cue

    cue = build_cue("まだ止まった刻む針も", 0, 4000, "ja")
    sung = "".join(tok["text"] for tok in cue["tokens"])
    assert "止" in sung
    assert "刻" in sung
    assert "針" in sung
    labels = "".join(tok["reading"] for tok in cue["tokens"] if tok["reading"])
    assert "とま" in labels
    assert "きざ" in labels
    assert "はり" in labels


def test_ja_katakana_fallback_is_unlabeled():
    from lovktv.pipeline.lyrics import build_cue

    cue = build_cue("ナイトダンサー", 0, 2000, "ja")
    assert "".join(tok["text"] for tok in cue["tokens"]) == "ナイトダンサー"
    assert all(not tok["reading"] for tok in cue["tokens"])
