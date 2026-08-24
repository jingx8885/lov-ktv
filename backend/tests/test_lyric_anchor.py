from lovktv.pipeline.align import align_lyrics
from lovktv.pipeline.lyric_anchor import align_lines_with_anchor, asr_words_to_segments


def _pulse(seconds: float, hop_ms: int = 20, bursts: list[tuple[float, float]] | None = None) -> list[float]:
    n = int(seconds * 1000 / hop_ms)
    env = [8.0] * n
    for start, end in bursts or []:
        for i in range(int(start * 1000 / hop_ms), min(n, int(end * 1000 / hop_ms))):
            env[i] = 220.0
    return env


def test_english_anchors_to_whisper_words():
    asr = [
        {"text": "What's", "start_ms": 85720, "end_ms": 86000},
        {"text": "waited", "start_ms": 86000, "end_ms": 86400},
        {"text": "till", "start_ms": 86400, "end_ms": 86640},
        {"text": "tomorrow", "start_ms": 86640, "end_ms": 87200},
        {"text": "starts", "start_ms": 88000, "end_ms": 88400},
        {"text": "tonight", "start_ms": 88400, "end_ms": 89000},
    ]
    bounds = align_lines_with_anchor(
        [{"ms": 85000, "text": "What's waited till tomorrow starts tonight"}],
        asr,
        "en",
    )
    assert bounds[0]["from_asr"]
    assert 85400 <= bounds[0]["start_ms"] <= 86000
    assert bounds[0]["end_ms"] >= 88400


def test_mandarin_anchors_character_line():
    asr = [
        {"text": "我听见", "start_ms": 1100, "end_ms": 1800},
        {"text": "雨", "start_ms": 1800, "end_ms": 2200},
        {"text": "落在", "start_ms": 4200, "end_ms": 4800},
        {"text": "窗台", "start_ms": 4800, "end_ms": 5400},
    ]
    bounds = align_lines_with_anchor(
        [{"ms": 1000, "text": "我听见雨"}, {"ms": 4100, "text": "落在窗台"}],
        asr,
        "zh",
    )
    assert bounds[0]["from_asr"] and bounds[1]["from_asr"]
    assert 1000 <= bounds[0]["start_ms"] <= 1300
    assert 4000 <= bounds[1]["start_ms"] <= 4400


def test_cantonese_anchors_like_cjk():
    asr = [
        {"text": "你喺我", "start_ms": 8000, "end_ms": 8600},
        {"text": "心里面", "start_ms": 8600, "end_ms": 9200},
        {"text": "冇人比你", "start_ms": 12000, "end_ms": 12800},
    ]
    bounds = align_lines_with_anchor(
        [{"ms": 7900, "text": "你喺我心裡面"}, {"ms": 11900, "text": "冇人比你更好"}],
        asr,
        "yue",
    )
    assert bounds[0]["from_asr"]
    assert 7800 <= bounds[0]["start_ms"] <= 8200
    assert 11800 <= bounds[1]["start_ms"] <= 12200


def test_japanese_skips_junk_before_real_onset():
    hop = 20
    env = _pulse(45, hop, [(33.94, 37.0), (36.96, 40.4)])
    asr = [
        {"text": "漢字", "start_ms": 27340, "end_ms": 29980},
        {"text": "字", "start_ms": 29980, "end_ms": 29980},
        {"text": "悲しい", "start_ms": 33660, "end_ms": 34800},
        {"text": "時間の", "start_ms": 34800, "end_ms": 35600},
        {"text": "群れが", "start_ms": 35600, "end_ms": 36960},
        {"text": "走り抜ける", "start_ms": 36960, "end_ms": 39000},
        {"text": "都市はサバンナ", "start_ms": 39000, "end_ms": 40340},
    ]
    bounds = align_lines_with_anchor(
        [
            {"ms": 33750, "text": "目まぐるしい 時間の群れが"},
            {"ms": 37000, "text": "走り抜ける 都市はサバンナ"},
        ],
        asr,
        "ja",
        envelope=env,
        hop_ms=hop,
    )
    assert 33200 <= bounds[0]["start_ms"] <= 34000
    assert bounds[0]["end_ms"] >= 36000
    assert bounds[1]["from_asr"]


def test_intro_keeps_official_when_whisper_hears_later_chorus():
    hop = 20
    env = _pulse(40, hop, [(1.0, 9.2), (27.72, 35.0)])
    asr = [
        {"text": "どうでもいいような夜だけど", "start_ms": 28580, "end_ms": 29800},
        {"text": "入り浸った散らかる部屋も", "start_ms": 29980, "end_ms": 34900},
    ]
    bounds = align_lines_with_anchor(
        [
            {"ms": 1050, "text": "どうでもいいような夜だけど"},
            {"ms": 4710, "text": "響めき煌めきと君も"},
            {"ms": 25060, "text": "まだ止まった刻む針も"},
            {"ms": 29000, "text": "入り浸った散らかる部屋も"},
        ],
        asr,
        "ja",
        envelope=env,
        hop_ms=hop,
    )
    assert abs(bounds[0]["start_ms"] - 1050) <= 80
    assert not bounds[0]["from_asr"]
    assert 27200 <= bounds[2]["start_ms"] <= 28200
    assert 29700 <= bounds[3]["start_ms"] <= 31000


def test_whisper_segment_ids_prevent_cjk_merge():
    segs = asr_words_to_segments(
        [
            {"text": "ど", "start_ms": 28580, "end_ms": 29980, "segment": 0},
            {"text": "いりびたった", "start_ms": 29980, "end_ms": 32220, "segment": 1},
            {"text": "散らかる部屋も", "start_ms": 32820, "end_ms": 34900, "segment": 1},
        ]
    )
    assert len(segs) == 2
    assert segs[0].text == "ど"
    assert "散らかる" in segs[1].text


def test_align_lyrics_uses_anchor_for_asr_words():
    timeline = align_lyrics(
        [{"ms": 15700, "text": "Gotta change my answering machine"}],
        "en",
        asr_words=[
            {"text": "Gotta", "start_ms": 15700, "end_ms": 15700},
            {"text": "change", "start_ms": 15700, "end_ms": 20020},
            {"text": "my", "start_ms": 20020, "end_ms": 20320},
            {"text": "answering", "start_ms": 20320, "end_ms": 21000},
            {"text": "machine", "start_ms": 21000, "end_ms": 21640},
        ],
        envelope=[],
    )
    assert timeline["alignment"] == "asr"
    tokens = timeline["cues"][0]["tokens"]
    assert [tok["text"] for tok in tokens] == ["Gotta", "change", "my", "answering", "machine"]
    assert tokens[1]["end_ms"] == 20020
