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
