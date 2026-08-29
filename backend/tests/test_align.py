from lovktv.pipeline.audio import energy_token_spans, snap_to_onset, vocal_regions
from lovktv.pipeline.bounds import (
    align_lines_to_asr,
    assign_plain_lines,
    restore_short_official_gaps,
)
from lovktv.pipeline.clock import consensus_line_start
from lovktv.pipeline.energy import guard_early_next_starts, merge_with_energy
from lovktv.pipeline.lyrics import timeline_from_lrc, tokenize
from lovktv.pipeline.matching import (
    asr_token_spans,
    best_asr_span,
    estimate_lrc_offset,
    match_score,
    match_threshold,
    vocal_phrases,
)
from lovktv.pipeline.orchestrator import align_lyrics


def _pulse(
    seconds: float, hop_ms: int = 20, bursts: list[tuple[float, float]] | None = None
) -> list[float]:
    n = int(seconds * 1000 / hop_ms)
    env = [8.0] * n
    for start, end in bursts or []:
        for i in range(int(start * 1000 / hop_ms), min(n, int(end * 1000 / hop_ms))):
            progress = (i - int(start * 1000 / hop_ms)) / max(
                int((end - start) * 1000 / hop_ms), 1
            )
            env[i] = 220.0 if progress < 0.35 else 90.0
    return env


def test_zh_ja_en_monotonic_and_full_text():
    hop = 20
    env = _pulse(8, hop, [(1.0, 3.2), (4.0, 6.5)])
    zh = align_lyrics(
        [{"ms": 1100, "text": "我听见雨"}, {"ms": 4200, "text": "落在窗台"}],
        "zh",
        envelope=env,
        hop_ms=hop,
        duration_ms=8000,
    )
    ja = align_lyrics(
        [{"ms": 1000, "text": "こんにちは"}, {"ms": 4000, "text": "世界"}],
        "ja",
        envelope=env,
        hop_ms=hop,
        duration_ms=8000,
    )
    en = align_lyrics(
        [{"ms": 1200, "text": "hello world"}, {"ms": 4100, "text": "again tonight"}],
        "en",
        envelope=env,
        hop_ms=hop,
        duration_ms=8000,
    )
    for timeline, expected in (
        (zh, ["我听见雨", "落在窗台"]),
        (ja, ["こんにちは", "世界"]),
        (en, ["hello world", "again tonight"]),
    ):
        assert timeline["alignment"] == "onset"
        assert [cue["text"] for cue in timeline["cues"]] == expected
        starts = [cue["start_ms"] for cue in timeline["cues"]]
        assert starts == sorted(starts)
        for cue in timeline["cues"]:
            assert cue["end_ms"] > cue["start_ms"]
            cursor = cue["start_ms"]
            for token in cue["tokens"]:
                assert token["start_ms"] >= cursor
                assert token["end_ms"] > token["start_ms"]
                cursor = token["end_ms"]
            pieces = tokenize(cue["text"], timeline["language"])
            assert [token["text"] for token in cue["tokens"]] == pieces


def test_english_does_not_use_cjk_threshold():
    assert match_threshold("en") > match_threshold("zh")
    asr = [
        {"text": "你好", "start_ms": 0, "end_ms": 900},
        {"text": "世界", "start_ms": 900, "end_ms": 1600},
    ]
    assert best_asr_span("I see you", asr, "en") is None
    assert match_score("I see you", "你好世界", "en") == 0.0
    assert best_asr_span("你好世界", asr, "zh") == (0, 1600)
    en_asr = [
        {"text": "hello", "start_ms": 1000, "end_ms": 1400},
        {"text": "world", "start_ms": 1400, "end_ms": 1900},
    ]
    assert best_asr_span("hello world", en_asr, "en") == (1000, 1900)


def test_energy_front_loaded_differs_from_even_split():
    hop = 20
    env = [200.0] * 20 + [10.0] * 80
    energy = energy_token_spans(0, 2000, 4, env, hop)
    even = energy_token_spans(0, 2000, 4, [], hop)
    assert energy[0][1] < even[0][1]
    assert energy[-1][1] == 2000


def test_plain_lyrics_land_on_vocal_regions():
    regions = [(1000, 2500), (4000, 6200)]
    rows = assign_plain_lines(["第一句", "第二句"], regions, 8000)
    assert rows[0]["ms"] == 1000
    assert rows[1]["ms"] == 4000
    env = _pulse(8, 20, [(1.0, 2.5), (4.0, 6.2)])
    timeline = align_lyrics(
        [{"ms": None, "text": "第一句"}, {"ms": None, "text": "第二句"}],
        "zh",
        envelope=env,
        hop_ms=20,
        duration_ms=8000,
    )
    assert timeline["alignment"] == "onset"
    assert timeline["cues"][0]["start_ms"] >= 800
    assert timeline["cues"][1]["start_ms"] >= 3500


def test_no_voice_falls_back_to_lrc_interp():
    timeline = align_lyrics(
        [{"ms": 0, "text": "晴天"}, {"ms": 1000, "text": "在下雨"}],
        "zh",
        envelope=[],
        duration_ms=2000,
    )
    assert timeline["alignment"] == "lrc-interp"
    assert timeline["cues"][0]["tokens"][0]["text"] == "晴"
    assert tokenize("晴天", "zh") == ["晴", "天"]


def test_lrc_gap_does_not_stretch_second_line():
    hop = 20
    env = _pulse(30, hop, [(1.0, 8.8), (25.0, 29.0)])
    lines = [
        {"ms": 1050, "text": "第一句歌词啊"},
        {"ms": 4710, "text": "第二句对不上", "end_ms": 9180},
        {"ms": 25060, "text": "主歌才开始"},
    ]
    timeline = align_lyrics(lines, "zh", envelope=env, hop_ms=hop, duration_ms=30000)
    second = timeline["cues"][1]
    assert second["start_ms"] == 4710
    assert 8000 <= second["end_ms"] <= 10000
    assert second["tokens"][-1]["end_ms"] == second["end_ms"]
    assert timeline["cues"][2]["start_ms"] == 25060


def test_snap_and_regions():
    env = _pulse(6, 20, [(2.0, 3.5)])
    regions = vocal_regions(env, 20)
    assert regions
    assert regions[0][0] >= 1800
    assert (
        snap_to_onset(2500, regions) == regions[0][0]
        or 1800 <= snap_to_onset(2500, regions) <= 2600
    )


def test_repeated_chorus_maps_to_later_asr():
    asr = [
        {"text": "どうでも", "start_ms": 9900, "end_ms": 10400},
        {"text": "いいような", "start_ms": 10400, "end_ms": 11200},
        {"text": "夜だけど", "start_ms": 11200, "end_ms": 13800},
        {"text": "ときめき", "start_ms": 13800, "end_ms": 15200},
        {"text": "まだ止まった", "start_ms": 25000, "end_ms": 27000},
        {"text": "刻む針も", "start_ms": 27000, "end_ms": 29000},
        {"text": "どうでも", "start_ms": 74600, "end_ms": 75100},
        {"text": "いいような", "start_ms": 75100, "end_ms": 76000},
        {"text": "夜だけど", "start_ms": 76000, "end_ms": 78400},
        {"text": "二人刻もう", "start_ms": 78400, "end_ms": 80200},
    ]
    lines = [
        {"ms": 9900, "text": "どうでもいいような夜だけど"},
        {"ms": 14000, "text": "ときめき煌めきと君も"},
        {"ms": 25060, "text": "まだ止まった刻む針も"},
        {"ms": 74610, "text": "どうでもいいような夜だけど"},
    ]
    timeline = align_lyrics(lines, "ja", asr_words=asr, envelope=[])
    assert timeline["alignment"] in {"asr", "lrc"}
    starts = [cue["start_ms"] for cue in timeline["cues"]]
    assert abs(starts[0] - 9900) <= 80
    assert abs(starts[2] - 25060) <= 80
    assert abs(starts[3] - 74610) <= 80
    assert starts[3] > starts[0]
    both = best_asr_span("どうでもいいような夜だけど", asr, "ja")
    assert both == (9900, 13800)


def test_asr_keeps_line_order_for_english_chorus():
    asr = [
        {"text": "hello", "start_ms": 1000, "end_ms": 1400},
        {"text": "world", "start_ms": 1400, "end_ms": 1900},
        {"text": "again", "start_ms": 2000, "end_ms": 2400},
        {"text": "hello", "start_ms": 10000, "end_ms": 10400},
        {"text": "world", "start_ms": 10400, "end_ms": 11000},
    ]
    bounds = align_lines_to_asr(
        [{"ms": 0, "text": "hello world"}, {"ms": 8000, "text": "hello world"}],
        asr,
        "en",
    )
    assert [row["start_ms"] for row in bounds] == [1000, 10000]


def test_small_lrc_jitter_does_not_shift():
    assert estimate_lrc_offset([{"ms": 1050, "text": "a"}], [(1000, 4000)]) == 0
    assert estimate_lrc_offset([{"ms": 1050, "text": "a"}], [(9900, 13000)]) == 8850


def test_late_vocals_shift_official_lrc():
    hop = 20
    env = _pulse(40, hop, [(9.9, 13.2), (25.0, 29.0)])
    phrases = vocal_phrases(vocal_regions(env, hop))
    assert phrases[0][0] >= 9000
    timeline = align_lyrics(
        [{"ms": 1050, "text": "第一句歌词啊"}, {"ms": 25060, "text": "主歌才开始"}],
        "zh",
        envelope=env,
        hop_ms=hop,
        duration_ms=40000,
    )
    assert timeline["cues"][0]["start_ms"] >= 9000
    assert timeline["cues"][1]["start_ms"] >= 33000


def test_timeline_from_lrc_still_covers_fixtures():
    ja = timeline_from_lrc(
        [{"ms": 0, "text": "こんにちは"}, {"ms": 1000, "text": "世界"}], "ja"
    )
    assert [tok["text"] for tok in ja["cues"][0]["tokens"]] == list("こんにちは")
    world = ja["cues"][1]["tokens"]
    assert "".join(tok["text"] for tok in world) == "".join(tokenize("世界", "ja"))
    assert any(tok["text"] == "世界" and tok["reading"] == "せかい" for tok in world)
    en = timeline_from_lrc(
        [{"ms": 0, "text": "hello world"}, {"ms": 2000, "text": "again"}], "en"
    )
    assert [tok["text"] for tok in en["cues"][0]["tokens"]] == ["hello", "world"]


def test_asr_skips_filler_before_official_lrc():
    asr = [
        {"text": "とっても", "start_ms": 780, "end_ms": 2000},
        {"text": "いいような", "start_ms": 2000, "end_ms": 3500},
        {"text": "夜だけど", "start_ms": 3500, "end_ms": 4760},
        {"text": "ときめき", "start_ms": 4760, "end_ms": 7000},
        {"text": "君も", "start_ms": 7000, "end_ms": 9300},
        {"text": "Ah", "start_ms": 9300, "end_ms": 10740},
        {"text": "まだ止まった", "start_ms": 25860, "end_ms": 28000},
        {"text": "刻む針も", "start_ms": 28000, "end_ms": 30320},
    ]
    lines = [
        {"ms": 1050, "text": "どうでもいいような夜だけど"},
        {"ms": 4710, "text": "ときめき煌めきと君も", "end_ms": 9180},
        {"ms": 25060, "text": "まだ止まった刻む針も"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja")
    assert bounds[2]["start_ms"] == 25860
    assert bounds[2]["end_ms"] == 30320
    assert bounds[1]["end_ms"] <= 10740


def test_short_chorus_tag_keeps_official_gap():
    bounds = [
        {"text": "Beautiful world", "start_ms": 37170, "end_ms": 37670},
        {"text": "迷わず君だけを見つめている", "start_ms": 37670, "end_ms": 45000},
    ]
    restore_short_official_gaps(
        bounds,
        [
            {"ms": 37170, "text": "Beautiful world"},
            {"ms": 38610, "text": "迷わず君だけを見つめている"},
        ],
        0,
    )
    assert bounds[0]["end_ms"] == 38610
    assert bounds[1]["start_ms"] == 38610


def test_zero_timestamp_title_does_not_shift_whole_song():
    asr = [
        {"text": "It's", "start_ms": 7940, "end_ms": 8500},
        {"text": "only", "start_ms": 8500, "end_ms": 9000},
        {"text": "love", "start_ms": 9000, "end_ms": 10000},
        {"text": "もしも", "start_ms": 18180, "end_ms": 20000},
        {"text": "願い", "start_ms": 20000, "end_ms": 22000},
        {"text": "一つだけ", "start_ms": 22000, "end_ms": 23180},
    ]
    lines = [
        {"ms": 0, "text": "It's only love"},
        {"ms": 13600, "text": "It's only love"},
        {"ms": 18800, "text": "もしも 願い 一つだけ"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja")
    assert 17000 <= bounds[2]["start_ms"] <= 20000
    assert bounds[2]["start_ms"] < 25000


def test_asr_offset_does_not_walk_away_from_official_lrc():
    asr = [
        {"text": "第一句比较长的歌词", "start_ms": 4000, "end_ms": 5200},
        {"text": "第二句也比较长啊", "start_ms": 15000, "end_ms": 16400},
        {"text": "第三句还是很长的", "start_ms": 27000, "end_ms": 28400},
        {"text": "第四句应当靠近原词", "start_ms": 30500, "end_ms": 32000},
        {"text": "第四句应当靠近原词", "start_ms": 40000, "end_ms": 41400},
    ]
    lines = [
        {"ms": 1000, "text": "第一句比较长的歌词"},
        {"ms": 10000, "text": "第二句也比较长啊"},
        {"ms": 20000, "text": "第三句还是很长的"},
        {"ms": 30000, "text": "第四句应当靠近原词"},
    ]
    bounds = align_lines_to_asr(lines, asr, "zh")
    assert 30000 <= bounds[3]["start_ms"] <= 33000
    assert bounds[3]["start_ms"] < 36000


def test_ja_leading_aah_still_matches_whisper():
    asr = [
        {"text": "愛して", "start_ms": 196900, "end_ms": 201860},
        {"text": "とてもいい", "start_ms": 201860, "end_ms": 203380},
    ]
    bounds = align_lines_to_asr(
        [
            {"ms": 186860, "text": "あぁ あぁ 愛して"},
            {"ms": 191640, "text": "どうでもいいから僕だけを"},
        ],
        asr,
        "ja",
    )
    assert bounds[0]["start_ms"] == 196900
    assert bounds[0]["end_ms"] == 201860


def test_ja_simplified_lrc_matches_whisper_kanji():
    asr = [
        {"text": "目まぐるしい", "start_ms": 33750, "end_ms": 35000},
        {"text": "時間の群れが", "start_ms": 35000, "end_ms": 37210},
        {"text": "走り抜ける", "start_ms": 37210, "end_ms": 39000},
    ]
    bounds = align_lines_to_asr(
        [
            {"ms": 0, "text": "「Give a reason」"},
            {"ms": 33750, "text": "目まぐるしい 时间の群れが"},
            {"ms": 37210, "text": "走り抜ける"},
        ],
        asr,
        "ja",
    )
    assert [row["text"] for row in bounds] == [
        "目まぐるしい 時間の群れが",
        "走り抜ける",
    ]
    assert bounds[0]["start_ms"] == 33750


def test_asr_fallback_keeps_verse_offset():
    """Late official LRC must not yank the next line after ASR found the verse early."""
    asr = [
        {"text": "嗚呼", "start_ms": 1000, "end_ms": 1400},
        {"text": "いつもの様に", "start_ms": 1400, "end_ms": 2800},
        {"text": "嗚呼", "start_ms": 72040, "end_ms": 72680},
        {"text": "手を伸ばせば伸ばすほどに", "start_ms": 72680, "end_ms": 76140},
        {"text": "遠くへゆく", "start_ms": 76140, "end_ms": 77920},
        {"text": "全然違う言葉", "start_ms": 91000, "end_ms": 93000},
    ]
    lines = [
        {"ms": 966, "text": "嗚呼いつもの様に"},
        {"ms": 75679, "text": "嗚呼手を伸ばせば伸ばすほどに"},
        {"ms": 79912, "text": "遠くへゆく"},
        {"ms": 83155, "text": "ただ情けなくて"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja")
    assert 71800 <= bounds[1]["start_ms"] <= 73000
    assert 75800 <= bounds[2]["start_ms"] <= 77000
    assert 78800 <= bounds[3]["start_ms"] <= 80000


def test_asr_does_not_steal_early_lrc_when_whisper_starts_late():
    asr = [
        {"text": "知らず", "start_ms": 24120, "end_ms": 25000},
        {"text": "知らず隠してた", "start_ms": 25000, "end_ms": 27360},
        {"text": "本当の声を", "start_ms": 27360, "end_ms": 28500},
    ]
    lines = [
        {"ms": 966, "text": "嗚呼いつもの様に"},
        {"ms": 3516, "text": "過ぎる日々にあくびが出る"},
        {"ms": 25865, "text": "知らず知らず隠してた"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja")
    assert bounds[0]["start_ms"] == 966
    assert bounds[1]["start_ms"] == 3516
    assert 24120 <= bounds[2]["start_ms"] <= 26000


def test_asr_token_spans_follow_whisper_words():
    pieces = ["Gotta", "change", "my", "answering", "machine"]
    asr = [
        {"text": "Gotta", "start_ms": 15700, "end_ms": 15700},
        {"text": "change", "start_ms": 15700, "end_ms": 20020},
        {"text": "my", "start_ms": 20020, "end_ms": 20320},
        {"text": "answering", "start_ms": 20320, "end_ms": 21000},
        {"text": "machine", "start_ms": 21000, "end_ms": 21640},
    ]
    spans = asr_token_spans(pieces, 15700, 22530, asr, "en")
    even = energy_token_spans(15700, 22530, 5, [], 20)
    assert spans is not None
    assert spans[0][0] == 15700
    assert spans[1][1] == 20020
    assert 19980 <= spans[2][0] <= 20100
    assert spans[3] == (20320, 21000)
    assert spans[-1][1] == 22530
    assert abs(spans[1][1] - even[1][1]) > 800


def test_asr_token_spans_fallback_when_words_mismatch():
    pieces = ["hello", "world"]
    asr = [
        {"text": "totally", "start_ms": 0, "end_ms": 400},
        {"text": "different", "start_ms": 400, "end_ms": 900},
    ]
    assert asr_token_spans(pieces, 0, 1000, asr, "en") is None


def test_asr_token_spans_follow_cjk_chars():
    pieces = ["你", "好", "世", "界"]
    asr = [{"text": "你好世界", "start_ms": 1000, "end_ms": 1800}]
    spans = asr_token_spans(pieces, 1000, 1800, asr, "zh")
    assert spans is not None
    assert spans[0][0] == 1000
    assert spans[2][0] >= 1300
    assert spans[-1][1] == 1800


def test_english_typo_line_does_not_clip_previous_radio():
    """So Sick 1:15-1:25: LRC 'calender i have' vs Whisper 'calendar ahead'."""
    asr = [
        {"text": "So", "start_ms": 75100, "end_ms": 75940},
        {"text": "why", "start_ms": 75940, "end_ms": 76280},
        {"text": "can't", "start_ms": 76280, "end_ms": 76780},
        {"text": "I", "start_ms": 76780, "end_ms": 76840},
        {"text": "turn", "start_ms": 76840, "end_ms": 77100},
        {"text": "off", "start_ms": 77100, "end_ms": 77480},
        {"text": "the", "start_ms": 77480, "end_ms": 77740},
        {"text": "radio?", "start_ms": 77740, "end_ms": 78400},
        {"text": "Gotta", "start_ms": 79900, "end_ms": 80320},
        {"text": "fix", "start_ms": 80320, "end_ms": 80680},
        {"text": "that", "start_ms": 80680, "end_ms": 80960},
        {"text": "calendar", "start_ms": 80960, "end_ms": 81600},
        {"text": "ahead", "start_ms": 81600, "end_ms": 82500},
        {"text": "let's", "start_ms": 82500, "end_ms": 83660},
        {"text": "mark", "start_ms": 83660, "end_ms": 83840},
        {"text": "July", "start_ms": 83840, "end_ms": 84140},
        {"text": "15th", "start_ms": 84140, "end_ms": 85200},
    ]
    bounds = align_lines_to_asr(
        [
            {"ms": 75460, "text": "So why can't i turn off the radio"},
            {"ms": 77790, "text": "Gotta fix that calender i have"},
            {"ms": 83080, "text": "That's marked july 15th"},
        ],
        asr,
        "en",
    )
    assert bounds[0]["end_ms"] >= 78400
    assert 79800 <= bounds[1]["start_ms"] <= 81000
    assert bounds[1]["end_ms"] >= 82000
    assert 82400 <= bounds[2]["start_ms"] <= 84000
    radio = asr_token_spans(
        ["So", "why", "can't", "i", "turn", "off", "the", "radio"],
        bounds[0]["start_ms"],
        bounds[0]["end_ms"],
        asr,
        "en",
    )
    assert radio is not None
    assert radio[-1][1] >= 78300
    assert radio[-1][1] > radio[-1][0]


def test_asr_rescues_line_after_instrumental_when_official_is_early():
    """NIGHT DANCER verse 2: official LRC sits in a hole, Whisper is ~6s later."""
    asr = [
        {"text": "二人", "start_ms": 91060, "end_ms": 92000},
        {"text": "刻もう", "start_ms": 92000, "end_ms": 93900},
        {"text": "突き通った", "start_ms": 112460, "end_ms": 114280},
        {"text": "白い肌も", "start_ms": 114820, "end_ms": 116700},
        {"text": "その笑った", "start_ms": 116700, "end_ms": 118760},
        {"text": "無邪気な顔も", "start_ms": 118760, "end_ms": 121220},
        {"text": "変わらないね", "start_ms": 121220, "end_ms": 122940},
        {"text": "変わらないで", "start_ms": 123240, "end_ms": 125100},
        {"text": "いられるのは", "start_ms": 125100, "end_ms": 127400},
        {"text": "今だけか", "start_ms": 127400, "end_ms": 129320},
    ]
    lines = [
        {"ms": 87150, "text": "2人刻もう"},
        {"ms": 106539, "text": "透き通った白い肌も"},
        {"ms": 110920, "text": "その笑った無邪気な顔も"},
        {"ms": 115100, "text": "変わらないね 変わらないで"},
        {"ms": 119100, "text": "居られるのは今だけか"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja")
    assert 111000 <= bounds[1]["start_ms"] <= 113500
    assert 115500 <= bounds[1]["end_ms"] <= 117500
    assert 116000 <= bounds[2]["start_ms"] <= 117800
    assert bounds[2]["end_ms"] <= 122000
    assert bounds[3]["start_ms"] >= 120500
    assert bounds[3]["end_ms"] - bounds[3]["start_ms"] > 1500
    assert bounds[4]["start_ms"] >= 124500
    assert bounds[4]["end_ms"] >= 128500


def test_early_official_does_not_crush_after_asr_caught_up():
    """Once ASR is ahead, an early official stamp must not flatten the next line."""
    hop = 20
    env = _pulse(150, hop, [(112.0, 144.0)])
    asr = [
        {"text": "浮つく心にコーヒーを", "start_ms": 134800, "end_ms": 139280},
        {"text": "乱れた部屋に", "start_ms": 139280, "end_ms": 141000},
        {"text": "掠れたメロディ", "start_ms": 141000, "end_ms": 143920},
    ]
    lines = [
        {"ms": 134800, "text": "浮つく心にコーヒーを"},
        {"ms": 132400, "text": "乱れた部屋に 掠れたメロディ"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja", envelope=env, hop_ms=hop)
    assert bounds[1]["start_ms"] >= 138000
    assert bounds[1]["end_ms"] - bounds[1]["start_ms"] > 1500


def test_late_whisper_keeps_official_when_vocals_already_there():
    """Chorus: official stamp has voice; Whisper words arrive a few seconds late."""
    hop = 20
    env = _pulse(90, hop, [(74.0, 88.0)])
    asr = [
        {"text": "どうでもいいような夜だけど", "start_ms": 78720, "end_ms": 82460},
        {"text": "ときめき煌めきと君も", "start_ms": 82460, "end_ms": 86540},
    ]
    lines = [
        {"ms": 74610, "text": "どうでもいいような夜だけど"},
        {"ms": 78510, "text": "ときめき煌めきと君も"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja", envelope=env, hop_ms=hop)
    assert abs(bounds[0]["start_ms"] - 74610) <= 200
    assert bounds[1]["start_ms"] <= 80000


def test_collapsed_asr_does_not_pull_first_line_early():
    """Give a reason: zero-width Whisper junk before the real onset."""
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
    lines = [
        {"ms": 33750, "text": "目まぐるしい 時間の群れが"},
        {"ms": 37000, "text": "走り抜ける 都市はサバンナ"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja", envelope=env, hop_ms=hop)
    assert 33200 <= bounds[0]["start_ms"] <= 34000
    assert bounds[0]["end_ms"] >= 36000


def test_unmatched_verse_snaps_to_voice_before_next_asr():
    """NIGHT DANCER L03: official stamp in a hole, next line already ASR-hit."""
    hop = 20
    env = _pulse(40, hop, [(1.0, 9.2), (27.72, 35.0)])
    asr = [
        {"text": "どうでもいいような夜だけど", "start_ms": 28580, "end_ms": 29800},
        {"text": "入り浸った散らかる部屋も", "start_ms": 29980, "end_ms": 34900},
        {"text": "変わらないね思い出しては", "start_ms": 34900, "end_ms": 39200},
    ]
    lines = [
        {"ms": 1050, "text": "どうでもいいような夜だけど"},
        {"ms": 4710, "text": "響めき煌めきと君も"},
        {"ms": 25060, "text": "まだ止まった刻む針も"},
        {"ms": 29000, "text": "入り浸った散らかる部屋も"},
    ]
    bounds = align_lines_to_asr(lines, asr, "ja", envelope=env, hop_ms=hop)
    assert bounds[0]["start_ms"] == 1050
    assert 27200 <= bounds[2]["start_ms"] <= 28200
    assert bounds[2]["end_ms"] >= 29500
    assert 29700 <= bounds[3]["start_ms"] <= 31000


def test_consensus_moves_when_whisper_and_onset_agree():
    hop = 20
    env = _pulse(20, hop, [(1.0, 8.5), (10.0, 16.0)])
    start, from_asr = consensus_line_start(
        official_ms=2500,
        asr_start=10000,
        regions=vocal_regions(env, hop),
        next_ms=16000,
        prev_end=0,
    )
    assert from_asr
    assert 9800 <= start <= 10400


def test_consensus_keeps_official_when_whisper_is_early():
    hop = 20
    env = _pulse(40, hop, [(32.6, 39.0)])
    start, from_asr = consensus_line_start(
        official_ms=35540,
        asr_start=33560,
        regions=vocal_regions(env, hop),
        next_ms=39050,
        prev_end=32710,
    )
    assert start == 35540
    assert not from_asr


def test_official_clock_ignores_early_whisper():
    hop = 20
    env = _pulse(40, hop, [(32.6, 39.0)])
    timeline = align_lyrics(
        [
            {"ms": 32710, "text": "美貌が许さないわ"},
            {"ms": 35540, "text": "どんな相手でも怯まないで"},
        ],
        "ja",
        asr_words=[
            {"text": "微妨が許せないわ", "start_ms": 32700, "end_ms": 34940},
            {"text": "どんな相手でも", "start_ms": 33560, "end_ms": 37120},
        ],
        envelope=env,
        hop_ms=hop,
    )
    assert abs(timeline["cues"][0]["start_ms"] - 32710) <= 80
    assert abs(timeline["cues"][1]["start_ms"] - 35540) <= 80
    assert timeline["cues"][0]["end_ms"] >= 35400


def test_energy_snaps_unmatched_hole_without_next_asr():
    hop = 20
    env = _pulse(20, hop, [(4.0, 7.2), (8.0, 11.0)])
    timeline = align_lyrics(
        [
            {"ms": 1000, "text": "first line sitting in a hole"},
            {"ms": 8000, "text": "second line on the voice"},
        ],
        "en",
        asr_words=[{"text": "anska", "start_ms": 0, "end_ms": 1800}],
        envelope=env,
        hop_ms=hop,
        duration_ms=20000,
    )
    assert 3800 <= timeline["cues"][0]["start_ms"] <= 4300
    assert abs(timeline["cues"][1]["start_ms"] - 8000) <= 200


def test_energy_does_not_steal_next_line_onset():
    hop = 20
    env = _pulse(45, hop, [(14.0, 33.5), (39.2, 44.0)])
    timeline = align_lyrics(
        [
            {"ms": 34307, "text": "But it feels like home"},
            {"ms": 39993, "text": "They can say they can say it all sounds crazy"},
        ],
        "en",
        asr_words=[{"text": "anska", "start_ms": 0, "end_ms": 1840}],
        envelope=env,
        hop_ms=hop,
        duration_ms=45000,
    )
    assert abs(timeline["cues"][0]["start_ms"] - 34307) <= 200
    assert abs(timeline["cues"][1]["start_ms"] - 39993) <= 200


def test_energy_keeps_official_when_voice_present():
    hop = 20
    env = _pulse(40, hop, [(14.0, 36.0)])
    timeline = align_lyrics(
        [
            {"ms": 14248, "text": "I close my eyes and I can see"},
            {"ms": 17494, "text": "The world that's waiting up for me"},
        ],
        "en",
        asr_words=[
            {"text": "anska", "start_ms": 0, "end_ms": 1840},
            {"text": "You", "start_ms": 66360, "end_ms": 67760},
        ],
        envelope=env,
        hop_ms=hop,
    )
    assert timeline["cues"][0]["start_ms"] == 14248
    assert abs(timeline["cues"][1]["start_ms"] - 17494) <= 80


def test_energy_does_not_chop_previous_end():
    hop = 20
    env = _pulse(160, hop, [(149.9, 151.3), (153.7, 159.7)])
    merged = merge_with_energy(
        [
            {
                "text": "力合わせ遥か先",
                "start_ms": 149920,
                "end_ms": 153720,
                "from_asr": True,
            },
            {
                "text": "未来に向かい步き続けて行く",
                "start_ms": 151620,
                "end_ms": 159580,
                "from_asr": True,
            },
        ],
        env,
        hop,
    )
    assert merged[0]["end_ms"] >= 153000
    assert merged[1]["start_ms"] >= merged[0]["end_ms"]


def test_guard_delays_next_line_started_in_a_hole():
    hop = 20
    env = _pulse(95, hop, [(76.0, 83.8), (86.16, 90.0)])
    bounds = guard_early_next_starts(
        [
            {
                "text": "限りないほど",
                "start_ms": 82460,
                "end_ms": 85000,
                "from_asr": True,
            },
            {
                "text": "Get along Try again",
                "start_ms": 85000,
                "end_ms": 93480,
                "from_asr": True,
            },
        ],
        [
            {"ms": 83100, "text": "限りないほど"},
            {"ms": 86300, "text": "Get along Try again"},
        ],
        env,
        hop,
    )
    assert bounds[1]["start_ms"] >= 85800
    assert bounds[0]["end_ms"] >= bounds[1]["start_ms"] - 20


def test_guard_does_not_pull_back_official_hole():
    hop = 20
    env = _pulse(120, hop, [(91.0, 94.0), (112.0, 121.0)])
    bounds = guard_early_next_starts(
        [
            {"text": "2人刻もう", "start_ms": 91060, "end_ms": 93900, "from_asr": True},
            {
                "text": "透き通った白い肌も",
                "start_ms": 112460,
                "end_ms": 116700,
                "from_asr": True,
            },
        ],
        [
            {"ms": 87150, "text": "2人刻もう"},
            {"ms": 106539, "text": "透き通った白い肌も"},
        ],
        env,
        hop,
    )
    assert 111000 <= bounds[1]["start_ms"] <= 113500


def test_energy_does_not_move_asr_hit():
    hop = 20
    env = _pulse(20, hop, [(2.0, 4.0), (8.0, 12.0)])
    timeline = align_lyrics(
        [{"ms": 8000, "text": "hello world tonight"}],
        "en",
        asr_words=[
            {"text": "hello", "start_ms": 8000, "end_ms": 8400},
            {"text": "world", "start_ms": 8400, "end_ms": 9000},
            {"text": "tonight", "start_ms": 9000, "end_ms": 9600},
        ],
        envelope=env,
        hop_ms=hop,
    )
    assert abs(timeline["cues"][0]["start_ms"] - 8000) <= 280


def test_align_lyrics_uses_asr_word_times():
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
    tokens = timeline["cues"][0]["tokens"]
    assert [tok["text"] for tok in tokens] == [
        "Gotta",
        "change",
        "my",
        "answering",
        "machine",
    ]
    assert tokens[1]["end_ms"] == 20020
    assert tokens[3]["start_ms"] == 20320
