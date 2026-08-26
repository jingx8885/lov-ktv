from lovktv.pipeline.align import align_lyrics
from lovktv.pipeline.lyric_anchor import (
    align_lines_with_anchor,
    asr_words_to_segments,
    merge_whisper_and_anchor,
)


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


def test_peel_short_next_line_off_merged_asr():
    bounds = align_lines_with_anchor(
        [
            {"ms": 70120, "text": "よそに揃い始めてた"},
            {"ms": 73180, "text": "息が"},
        ],
        [
            {"text": "揃い始めてた", "start_ms": 74580, "end_ms": 77800},
            {"text": "息が", "start_ms": 77800, "end_ms": 78720},
        ],
        "ja",
    )
    assert bounds[0]["from_asr"] and bounds[1]["from_asr"]
    assert bounds[0]["end_ms"] <= bounds[1]["start_ms"]
    assert bounds[1]["end_ms"] - bounds[1]["start_ms"] >= 700
    assert bounds[1]["start_ms"] >= 77600


def test_chorus_does_not_eat_next_hook():
    bounds = align_lines_with_anchor(
        [
            {"ms": 74610, "text": "どうでもいいような夜だけど"},
            {"ms": 78510, "text": "響めき煌めきと君も"},
        ],
        [
            {"text": "とってもいい", "start_ms": 78720, "end_ms": 80300, "segment": 0},
            {"text": "いいような夜だけど", "start_ms": 80300, "end_ms": 82460, "segment": 1},
            {"text": "どひょうめききらめきときみも", "start_ms": 82460, "end_ms": 86540, "segment": 2},
        ],
        "ja",
    )
    assert bounds[0]["from_asr"] and bounds[1]["from_asr"]
    assert bounds[0]["end_ms"] <= bounds[1]["start_ms"]
    assert bounds[1]["end_ms"] - bounds[1]["start_ms"] >= 2500
    assert bounds[1]["start_ms"] >= 82000


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


def test_merge_keeps_whisper_clock_when_anchor_drifts():
    whisper = [
        {"text": "I close my eyes", "start_ms": 14248, "end_ms": 17494, "from_asr": False},
        {"text": "The world that's waiting", "start_ms": 17494, "end_ms": 21195, "from_asr": False},
    ]
    anchor = [
        {"text": "I close my eyes", "start_ms": 0, "end_ms": 500, "from_asr": False},
        {"text": "The world that's waiting", "start_ms": 500, "end_ms": 1000, "from_asr": False},
    ]
    merged = merge_whisper_and_anchor(whisper, anchor)
    assert [row["start_ms"] for row in merged] == [14248, 17494]


def test_merge_takes_nearby_anchor_span():
    whisper = [
        {"text": "よそに揃い始めてた", "start_ms": 74580, "end_ms": 78720, "from_asr": True},
        {"text": "息が", "start_ms": 78720, "end_ms": 79220, "from_asr": False},
    ]
    anchor = [
        {"text": "よそに揃い始めてた", "start_ms": 74580, "end_ms": 77800, "from_asr": True},
        {"text": "息が", "start_ms": 77800, "end_ms": 78720, "from_asr": True},
    ]
    merged = merge_whisper_and_anchor(whisper, anchor)
    assert merged[0]["end_ms"] <= merged[1]["start_ms"]
    assert merged[1]["from_asr"]
    assert merged[1]["start_ms"] == 77800


def test_merge_does_not_chop_rescued_line():
    """Get along: Whisper misses 美貌が许さないわ and starts the next line on が."""
    whisper = [
        {"text": "誰もがうらやむこのパワーと", "start_ms": 28720, "end_ms": 32340, "from_asr": True},
        {"text": "美貌が许さないわ", "start_ms": 32340, "end_ms": 33560, "from_asr": False},
        {"text": "どんな相手でも怯まないで", "start_ms": 33560, "end_ms": 39320, "from_asr": True},
    ]
    anchor = [
        {"text": "誰もがうらやむこのパワーと", "start_ms": 28720, "end_ms": 32620, "from_asr": True},
        {"text": "美貌が许さないわ", "start_ms": 32620, "end_ms": 34940, "from_asr": True},
        {"text": "どんな相手でも怯まないで", "start_ms": 34940, "end_ms": 38740, "from_asr": True},
    ]
    merged = merge_whisper_and_anchor(whisper, anchor)
    assert merged[1]["from_asr"]
    assert merged[1]["end_ms"] >= 34600
    assert merged[1]["end_ms"] - merged[1]["start_ms"] >= 1800
    assert merged[2]["start_ms"] >= merged[1]["end_ms"]


def test_junk_asr_keeps_official_clock():
    timeline = align_lyrics(
        [
            {"ms": 14248, "text": "I close my eyes and I can see"},
            {"ms": 17494, "text": "The world that's waiting up for me"},
            {"ms": 21195, "text": "That I call my own"},
            {"ms": 27491, "text": "Through the dark through the door"},
        ],
        "en",
        asr_words=[
            {"text": "anska", "start_ms": 0, "end_ms": 1840},
            {"text": "You", "start_ms": 66360, "end_ms": 67760},
        ],
        envelope=[],
    )
    starts = [cue["start_ms"] for cue in timeline["cues"]]
    assert starts[0] == 14248
    assert abs(starts[1] - 17494) <= 80
    assert abs(starts[2] - 21195) <= 80
    assert abs(starts[3] - 27491) <= 80


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
    assert timeline["alignment"] in {"asr", "lrc"}
    tokens = timeline["cues"][0]["tokens"]
    assert [tok["text"] for tok in tokens] == ["Gotta", "change", "my", "answering", "machine"]
    assert tokens[1]["end_ms"] == 20020
