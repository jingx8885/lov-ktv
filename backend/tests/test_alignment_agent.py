import json

from lovktv.agents import alignment
from lovktv.pipeline.orchestrator import align_lyrics


def test_agent_matches_are_validated_and_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_AGENT_URL", "http://agent.test")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "test-key")
    monkeypatch.setattr(alignment, "_complete", lambda messages: [
        {"lyric": 1, "from": 1, "to": 2},
        {"lyric": 2, "from": 3, "to": 3},
        {"lyric": 2, "from": 4, "to": 4},  # duplicate lyric
        {"lyric": 3, "from": 2, "to": 1},  # reversed span
    ])
    got = alignment.align_lines_with_agent(
        [{"text": "hello"}, {"text": "world"}],
        [
            {"text": "hello", "start_ms": 100, "end_ms": 200},
            {"text": "there", "start_ms": 200, "end_ms": 300},
            {"text": "world", "start_ms": 300, "end_ms": 400},
        ],
        "en",
        cache_path=tmp_path / "agent-align.json",
    )
    assert got == [
        {"lyric": 1, "from": 1, "to": 2},
        {"lyric": 2, "from": 3, "to": 3},
    ]
    cached = json.loads((tmp_path / "agent-align.json").read_text(encoding="utf-8"))
    assert cached["schema"] == alignment.ALIGN_SCHEMA


def test_agent_prompt_keeps_grok_word_level_times(monkeypatch):
    monkeypatch.setenv("LOVKTV_AGENT_URL", "http://agent.test")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "test-key")
    seen = {}

    def complete(messages):
        seen["text"] = messages[1]["content"]
        return [{"lyric": 1, "from": 1, "to": 1}]

    monkeypatch.setattr(alignment, "_complete", complete)
    alignment.align_lines_with_agent(
        [{"ms": 12_000, "text": "hello"}],
        [{"text": "hello", "start_ms": 12_340, "end_ms": 12_780}],
        "en",
    )
    assert "[12340-12780] hello" in seen["text"]


def test_orchestrator_uses_agent_word_times():
    timeline = align_lyrics(
        [{"ms": 0, "text": "hello world"}, {"ms": 3000, "text": "again"}],
        "en",
        asr_words=[
            {"text": "hello", "start_ms": 1000, "end_ms": 1400},
            {"text": "world", "start_ms": 1400, "end_ms": 1800},
            {"text": "again", "start_ms": 5000, "end_ms": 5400},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 2},
            {"lyric": 2, "from": 3, "to": 3},
        ],
    )
    assert timeline["alignment"] == "agent"
    assert [cue["start_ms"] for cue in timeline["cues"]] == [1000, 5000]


def test_agent_word_times_are_not_clipped_by_old_next_lrc_clock():
    timeline = align_lyrics(
        [{"ms": 10_000, "text": "hello world"}, {"ms": 11_000, "text": "again"}],
        "en",
        asr_words=[
            {"text": "hello", "start_ms": 20_000, "end_ms": 20_500},
            {"text": "world", "start_ms": 20_500, "end_ms": 21_000},
            {"text": "again", "start_ms": 22_000, "end_ms": 22_500},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 2},
            {"lyric": 2, "from": 3, "to": 3},
        ],
    )
    assert timeline["alignment"] == "agent"
    assert [cue["start_ms"] for cue in timeline["cues"]] == [20_000, 22_000]


def test_sparse_agent_anchors_interpolate_version_drift_without_cascade():
    timeline = align_lyrics(
        [
            {"ms": 23_110, "text": "I saw the sun"},
            {"ms": 25_990, "text": "And felt the wind"},
            {"ms": 28_250, "text": "Blow cold"},
            {"ms": 33_820, "text": "A man learns"},
        ],
        "en",
        duration_ms=40_000,
        asr_words=[
            {"text": "I", "start_ms": 0, "end_ms": 500},
            {"text": "saw", "start_ms": 500, "end_ms": 1_000},
            {"text": "the", "start_ms": 1_000, "end_ms": 1_500},
            {"text": "And", "start_ms": 2_340, "end_ms": 2_840},
            {"text": "felt", "start_ms": 2_840, "end_ms": 3_340},
            {"text": "the", "start_ms": 3_340, "end_ms": 3_840},
            {"text": "A", "start_ms": 10_280, "end_ms": 10_780},
            {"text": "man", "start_ms": 10_780, "end_ms": 11_280},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 3},
            {"lyric": 2, "from": 4, "to": 6},
            {"lyric": 4, "from": 7, "to": 8},
        ],
    )
    assert timeline["alignment_source"] == "agent+whisper-drift"
    starts = [cue["start_ms"] for cue in timeline["cues"]]
    assert starts[0:2] == [0, 2_340]
    assert 4_000 <= starts[2] <= 5_500
    assert starts[3] == 10_280


def test_complete_agent_match_keeps_official_clock_even_with_duration_tail():
    timeline = align_lyrics(
        [
            {"ms": 10_000, "text": "hello world"},
            {"ms": 14_000, "text": "again now"},
            {"ms": 18_000, "text": "good night"},
            {"ms": 22_000, "text": "see you"},
        ],
        "en",
        duration_ms=25_000,
        asr_words=[
            {"text": "hello", "start_ms": 9_900, "end_ms": 10_400},
            {"text": "world", "start_ms": 10_400, "end_ms": 10_900},
            {"text": "again", "start_ms": 13_900, "end_ms": 14_400},
            {"text": "now", "start_ms": 14_400, "end_ms": 14_900},
            {"text": "good", "start_ms": 17_900, "end_ms": 18_400},
            {"text": "night", "start_ms": 18_400, "end_ms": 18_900},
            {"text": "see", "start_ms": 21_900, "end_ms": 22_400},
            {"text": "you", "start_ms": 22_400, "end_ms": 22_900},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 2},
            {"lyric": 2, "from": 3, "to": 4},
            {"lyric": 3, "from": 5, "to": 6},
            {"lyric": 4, "from": 7, "to": 8},
        ],
    )
    assert timeline["alignment_source"] == "agent+whisper"
    assert [cue["start_ms"] for cue in timeline["cues"]] == [9_900, 13_900, 17_900, 21_900]


def test_orchestrator_switches_to_consistent_asr_clock_for_version_drift():
    timeline = align_lyrics(
        [
            {"ms": 20_000, "text": "hello world"},
            {"ms": 24_000, "text": "again now"},
            {"ms": 28_000, "text": "hello world"},
        ],
        "en",
        asr_words=[
            {"text": "hello", "start_ms": 1000, "end_ms": 1400},
            {"text": "world", "start_ms": 1400, "end_ms": 1800},
            {"text": "again", "start_ms": 5000, "end_ms": 5400},
            {"text": "now", "start_ms": 5400, "end_ms": 5800},
            {"text": "hello", "start_ms": 9000, "end_ms": 9400},
            {"text": "world", "start_ms": 9400, "end_ms": 9800},
        ],
    )
    assert timeline["alignment_source"] == "whisper"
    assert [cue["start_ms"] for cue in timeline["cues"]] == [1000, 5000, 9000]


def test_orchestrator_reorders_edited_media_from_agent_matches():
    timeline = align_lyrics(
        [
            {"ms": 0, "text": "first"},
            {"ms": 1000, "text": "chorus"},
            {"ms": 2000, "text": "second"},
        ],
        "en",
        asr_words=[
            {"text": "first", "start_ms": 100, "end_ms": 500},
            {"text": "second", "start_ms": 700, "end_ms": 1100},
            {"text": "chorus", "start_ms": 1500, "end_ms": 1900},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 1},
            {"lyric": 3, "from": 2, "to": 2},
            {"lyric": 2, "from": 3, "to": 3},
        ],
    )
    assert timeline["alignment_source"] == "agent+whisper-reordered"
    assert [cue["text"] for cue in timeline["cues"]] == ["first", "second", "chorus"]
    assert [cue["start_ms"] for cue in timeline["cues"]] == [100, 700, 1500]


def test_sparse_reorder_matches_fall_back_without_dropping_lyric_rows():
    lines = [{"ms": i * 1000, "text": text} for i, text in enumerate(
        ["one", "two", "three", "four", "five"]
    )]
    timeline = align_lyrics(
        lines,
        "en",
        asr_words=[
            {"text": "one", "start_ms": 100, "end_ms": 300},
            {"text": "three", "start_ms": 700, "end_ms": 900},
            {"text": "five", "start_ms": 1300, "end_ms": 1500},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 1},
            {"lyric": 3, "from": 2, "to": 2},
            {"lyric": 5, "from": 3, "to": 3},
        ],
        duration_ms=2000,
    )
    assert len(timeline["cues"]) == len(lines)
    assert [cue["text"] for cue in timeline["cues"]] == [x["text"] for x in lines]


def test_wrong_lyric_version_uses_asr_text_instead_of_interpolating_stale_lrc():
    timeline = align_lyrics(
        [
            {"ms": 0, "text": "opening line"},
            {"ms": 20_000, "text": "old second line"},
            {"ms": 40_000, "text": "old third line"},
            {"ms": 60_000, "text": "old fourth line"},
        ],
        "en",
        duration_ms=80_000,
        asr_words=[
            {"text": "opening", "start_ms": 0, "end_ms": 300},
            {"text": "line", "start_ms": 300, "end_ms": 600},
            {"text": "actual", "start_ms": 20_000, "end_ms": 20_300},
            {"text": "verse", "start_ms": 20_300, "end_ms": 20_600},
            {"text": "different", "start_ms": 40_000, "end_ms": 40_300},
            {"text": "words", "start_ms": 40_300, "end_ms": 40_600},
            {"text": "final", "start_ms": 60_000, "end_ms": 60_300},
            {"text": "line", "start_ms": 60_300, "end_ms": 60_600},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 2},
            {"lyric": 2, "from": 3, "to": 4},
            {"lyric": 3, "from": 5, "to": 6},
            {"lyric": 4, "from": 7, "to": 8},
        ],
    )
    assert timeline["alignment_source"] == "whisper-transcript-fallback"
    text = " ".join(cue["text"] for cue in timeline["cues"])
    assert "actual verse" in text
    assert "old second line" not in text


def test_cjk_wrong_lyric_version_is_detected_with_sparse_agent_anchors():
    timeline = align_lyrics(
        [{"ms": i * 10_000, "text": text} for i, text in enumerate(
            ["開場歌詞", "舊第二句", "舊第三句", "舊第四句", "舊第五句"]
        )],
        "zh",
        duration_ms=50_000,
        asr_words=[
            {"text": "開場歌詞", "start_ms": 0, "end_ms": 500},
            {"text": "實際第二句", "start_ms": 20_000, "end_ms": 20_500},
            {"text": "實際第三句", "start_ms": 30_000, "end_ms": 30_500},
            {"text": "實際第四句", "start_ms": 40_000, "end_ms": 40_500},
        ],
        agent_matches=[
            {"lyric": 1, "from": 1, "to": 1},
            {"lyric": 2, "from": 2, "to": 2},
            {"lyric": 3, "from": 3, "to": 3},
            {"lyric": 4, "from": 4, "to": 4},
        ],
    )
    assert timeline["alignment_source"] == "whisper-transcript-fallback"
    text = " ".join(cue["text"] for cue in timeline["cues"])
    assert "實際第二句" in text
    assert "舊第二句" not in text
