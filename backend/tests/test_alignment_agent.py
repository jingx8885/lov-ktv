import json

import pytest

from lovktv.agents import alignment
from lovktv.domain.alignment import parse_sung_lyrics
from lovktv.pipeline.energy import lrc_energy_match
from lovktv.pipeline.orchestrator import align_lyrics, resolve_sung_rows


def _words(*spec: tuple[str, int, int]) -> list[dict]:
    return [
        {"text": text, "start_ms": start, "end_ms": end} for text, start, end in spec
    ]


def test_lrc_energy_match_accepts_starts_near_vocal_onsets():
    # 20 ms hop; two vocal bursts begin at 1000 and 3000 ms.
    envelope = [0.0] * 250
    for start, end in ((50, 80), (150, 180)):
        for index in range(start, end):
            envelope[index] = 100.0
    result = lrc_energy_match(
        [{"ms": 1000, "text": "one"}, {"ms": 3020, "text": "two"}],
        envelope,
        hop_ms=20,
    )
    assert result["accepted"] is True
    assert result["matched"] == 2


def test_lrc_energy_match_rejects_when_no_vocal_onsets_match():
    envelope = [0.0] * 250
    for index in range(150, 180):
        envelope[index] = 100.0
    result = lrc_energy_match(
        [{"ms": 100, "text": "wrong"}, {"ms": 500, "text": "also wrong"}],
        envelope,
        hop_ms=20,
    )
    assert result["accepted"] is False


def _agent(monkeypatch, payload: dict) -> dict:
    monkeypatch.setenv("LOVKTV_AGENT_URL", "http://agent.test")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "test-key")
    seen: dict = {"calls": []}

    def request(messages):
        seen["calls"].append(messages[1]["content"])
        return json.dumps(payload)

    monkeypatch.setattr(alignment, "_request_content", request)
    return seen


# --- protocol -----------------------------------------------------------------


def test_sung_lyrics_reject_overlapping_or_backwards_spans():
    with pytest.raises(ValueError):
        parse_sung_lyrics(
            {
                "rows": [
                    {"text": "a", "from": 1, "to": 3},
                    {"text": "b", "from": 3, "to": 4},
                ]
            },
            word_count=4,
        )
    with pytest.raises(ValueError):
        parse_sung_lyrics(
            {
                "rows": [
                    {"text": "a", "from": 4, "to": 5},
                    {"text": "b", "from": 1, "to": 2},
                ]
            },
            word_count=5,
        )
    with pytest.raises(ValueError):
        parse_sung_lyrics({"rows": [{"text": "a", "from": 1, "to": 9}]}, word_count=4)


def test_sung_lyrics_need_one_anchor_and_accept_inferred_rows():
    with pytest.raises(ValueError):
        parse_sung_lyrics(
            {"rows": [{"text": "a", "status": "inferred", "reason": "x"}]}
        )
    parsed = parse_sung_lyrics(
        {
            "rows": [
                {"text": "first", "from": 1, "to": 1},
                {"text": "missed", "reason": "verse continues"},
                {"text": "third", "from": 2, "to": 2},
            ]
        },
        word_count=2,
    )
    assert [row.status for row in parsed.rows] == ["matched", "inferred", "matched"]


# --- agent adapter -------------------------------------------------------------


def test_generate_sung_lyrics_uses_transcript_and_caches(tmp_path, monkeypatch):
    seen = _agent(
        monkeypatch,
        {
            "schema": "lovktv-sung-lyrics-v1",
            "language": "en",
            "rows": [
                {
                    "text": "From now on",
                    "from": 1,
                    "to": 3,
                    "ref": 1,
                    "translation": "从现在起",
                    "tokens": [
                        {"surface": "From", "translation": "从"},
                        {"surface": "now", "translation": "现在"},
                        {"surface": "on", "translation": "起"},
                    ],
                },
                {
                    "text": "And we will come back home",
                    "from": 4,
                    "to": 8,
                    "ref": None,
                    "translation": "我们终将回家",
                },
            ],
        },
    )
    words = _words(
        ("from", 12_340, 12_500),
        ("now", 12_500, 12_700),
        ("on", 12_700, 12_900),
        ("and", 14_000, 14_100),
        ("we", 14_100, 14_200),
        ("will", 14_200, 14_300),
        ("come", 14_300, 14_500),
        ("back", 14_500, 14_700),
        ("home", 14_700, 15_000),
    )
    result = alignment.generate_sung_lyrics(
        [{"ms": 0, "text": "From now on"}, {"ms": 5000, "text": "Studio only line"}],
        words,
        "en",
        cache_path=tmp_path / "agent-align.json",
        energy_regions=[(0, 1000), (5000, 6000)],
    )
    assert result is not None
    assert [row.text for row in result.lyrics.rows] == [
        "From now on",
        "And we will come back home",
    ]
    assert result.lyrics.rows[0].ref == 1 and result.lyrics.rows[1].ref is None
    assert "[12340-12500] from" in seen["calls"][0]
    assert "1. From now on" in seen["calls"][0]
    assert "Vocal-energy regions" in seen["calls"][0]
    assert "0-1000ms" in seen["calls"][0]
    cached = json.loads((tmp_path / "agent-align.json").read_text(encoding="utf-8"))
    assert cached["schema"] == "lovktv-sung-lyrics-v1"

    # Second call hits the cache and never asks the model again.
    again = alignment.generate_sung_lyrics(
        [{"ms": 0, "text": "From now on"}, {"ms": 5000, "text": "Studio only line"}],
        words,
        "en",
        cache_path=tmp_path / "agent-align.json",
        energy_regions=[(0, 1000), (5000, 6000)],
    )
    assert again is not None and len(seen["calls"]) == 1


def test_generate_sung_lyrics_returns_none_on_invalid_answer(monkeypatch):
    _agent(monkeypatch, {"rows": []})
    assert (
        alignment.generate_sung_lyrics(
            [{"text": "a"}], _words(("a", 0, 100), ("b", 100, 200)), "en"
        )
        is None
    )


def test_generate_sung_lyrics_recovers_overlap_by_windowing(monkeypatch):
    # A whole-song answer with a reused word fails strict validation; the
    # windowed retry keeps the first claim on the words and drops the other.
    _agent(
        monkeypatch,
        {
            "rows": [
                {"text": "a", "from": 1, "to": 2},
                {"text": "b", "from": 2, "to": 3},
            ]
        },
    )
    result = alignment.generate_sung_lyrics(
        [{"text": "a"}], _words(("a", 0, 100), ("b", 100, 200), ("c", 200, 300)), "en"
    )
    assert result is not None and [row.text for row in result.lyrics.rows] == ["a"]


def test_generate_sung_lyrics_windows_long_transcripts(monkeypatch):
    monkeypatch.setattr(alignment, "_WHOLE_SONG_WORDS", 4)
    monkeypatch.setattr(alignment, "_WINDOW_WORDS", 3)
    monkeypatch.setattr(alignment, "_WINDOW_SEARCH", 1)
    monkeypatch.setenv("LOVKTV_AGENT_URL", "http://agent.test")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "test-key")
    calls: list[str] = []

    def request(messages):
        body = messages[1]["content"]
        calls.append(body)
        if "words 1-3" in body:
            return json.dumps({"rows": [{"text": "one two three", "from": 1, "to": 3}]})
        # A window may only claim its own words; the stray span is dropped.
        return json.dumps(
            {
                "rows": [
                    {"text": "stray", "from": 2, "to": 2},
                    {"text": "four five six", "from": 4, "to": 6},
                ]
            }
        )

    monkeypatch.setattr(alignment, "_request_content", request)
    result = alignment.generate_sung_lyrics(
        [],
        _words(
            ("one", 0, 100),
            ("two", 100, 200),
            ("three", 200, 300),
            ("four", 5_000, 5_100),
            ("five", 5_100, 5_200),
            ("six", 5_200, 5_300),
        ),
        "en",
    )
    assert result is not None
    assert [row.text for row in result.lyrics.rows] == [
        "one two three",
        "four five six",
    ]
    assert len(calls) == 2 and "do not repeat" in calls[1]


# --- timing resolution ---------------------------------------------------------


def test_resolve_sung_rows_takes_word_times_in_transcript_order():
    words = alignment.agent_words(
        _words(("first", 100, 500), ("second", 700, 1100), ("chorus", 1500, 1900))
    )
    rows = resolve_sung_rows(
        [
            {"text": "first", "from": 1, "to": 1},
            {"text": "second", "from": 2, "to": 2},
            {"text": "chorus", "from": 3, "to": 3},
        ],
        words,
        "en",
    )
    assert [(row["start_ms"], row["end_ms"]) for row in rows] == [
        (100, 700),
        (700, 1500),
        (1500, 1900),
    ]


def test_incomplete_line_is_extended_toward_next_line():
    words = alignment.agent_words(
        _words(("from", 0, 200), ("now", 200, 400), ("hello", 6_000, 6_300))
    )
    rows = resolve_sung_rows(
        [
            {"text": "From now on these eyes will not be blinded", "from": 1, "to": 2},
            {"text": "hello", "from": 3, "to": 3},
        ],
        words,
        "en",
    )
    # 7 unheard tokens * 350 ms = 2450 ms past the last heard word.
    assert rows[0]["end_ms"] == 400 + 7 * 350
    assert rows[0]["end_ms"] < rows[1]["start_ms"]


def test_inferred_line_shares_the_gap_between_neighbours():
    words = alignment.agent_words(_words(("first", 0, 1_000), ("third", 7_000, 8_000)))
    rows = resolve_sung_rows(
        [
            {"text": "first", "from": 1, "to": 1},
            {
                "text": "a missed second line",
                "status": "inferred",
                "reason": "verse continues",
            },
            {"text": "third", "from": 2, "to": 2},
        ],
        words,
        "en",
    )
    assert [row["text"] for row in rows] == ["first", "a missed second line", "third"]
    assert rows[1]["start_ms"] == 1_000 and rows[1]["end_ms"] == 7_000


def test_inferred_line_without_gap_borrows_time_from_previous_line():
    words = alignment.agent_words(_words(("first", 0, 1_000), ("third", 1_050, 2_000)))
    rows = resolve_sung_rows(
        [
            {"text": "first", "from": 1, "to": 1},
            {
                "text": "missed but sung",
                "status": "inferred",
                "reason": "verse continues",
            },
            {"text": "third", "from": 2, "to": 2},
        ],
        words,
        "en",
    )
    assert [row["text"] for row in rows] == ["first", "missed but sung", "third"]
    assert rows[0]["end_ms"] == rows[1]["start_ms"] == 250
    assert rows[1]["end_ms"] == rows[2]["start_ms"] == 1_050


def test_inferred_run_is_dropped_when_gap_has_no_vocal_energy(monkeypatch):
    # The agent may infer a chorus from reference line order, but an
    # instrumental break must not acquire lyrics.  Regions at the anchors are
    # intentionally ignored by the interior-energy guard.
    monkeypatch.setattr(
        "lovktv.pipeline.orchestrator._vocal_regions",
        lambda envelope, hop_ms: [(0, 100), (9_900, 10_100)],
    )
    words = alignment.agent_words(_words(("first", 0, 100), ("last", 10_000, 10_100)))
    rows = resolve_sung_rows(
        [
            {"text": "first", "from": 1, "to": 1},
            {"text": "instrumental chorus", "status": "inferred", "reason": "gap"},
            {"text": "last", "from": 2, "to": 2},
        ],
        words,
        "en",
        envelope=[1.0],
        hop_ms=20,
    )
    assert [row["text"] for row in rows] == ["first", "last"]


def test_half_heard_line_is_completed_from_reference(monkeypatch):
    _agent(
        monkeypatch,
        {"rows": [{"text": "From now on these", "from": 1, "to": 4, "ref": 1}]},
    )
    result = alignment.generate_sung_lyrics(
        [{"ms": 0, "text": "From now on these eyes will not be blinded by the lights"}],
        _words(
            ("from", 0, 100), ("now", 100, 200), ("on", 200, 300), ("these", 300, 400)
        ),
        "en",
    )
    assert result is not None
    assert (
        result.lyrics.rows[0].text
        == "From now on these eyes will not be blinded by the lights"
    )


# --- orchestrator --------------------------------------------------------------


def test_align_lyrics_builds_timeline_from_sung_rows_not_reference():
    asr = _words(
        ("opening", 0, 300),
        ("line", 300, 600),
        ("actual", 20_000, 20_300),
        ("verse", 20_300, 20_600),
    )
    words = alignment.agent_words(asr)
    timeline = align_lyrics(
        [
            {"ms": 0, "text": "opening line"},
            {"ms": 20_000, "text": "old second line"},
            {"ms": 40_000, "text": "old third line"},
        ],
        "en",
        duration_ms=60_000,
        asr_words=asr,
        sung_rows=[
            {
                "text": "opening line",
                "from": 1,
                "to": 2,
                "ref": 1,
                "translation": "开场",
                "tokens": [
                    {"surface": "opening", "translation": "开"},
                    {"surface": "line", "translation": "场"},
                ],
            },
            {
                "text": "Actual verse",
                "from": 3,
                "to": 4,
                "ref": None,
                "translation": "真实段落",
            },
        ],
        sung_words=words,
    )
    assert timeline["alignment_source"] == "agent+asr"
    assert [cue["text"] for cue in timeline["cues"]] == ["opening line", "Actual verse"]
    assert [cue["start_ms"] for cue in timeline["cues"]] == [0, 20_000]
    first = timeline["cues"][0]
    assert first["zh"] == "开场"
    assert [token["zh"] for token in first["tokens"]] == ["开", "场"]
    assert [(token["start_ms"], token["end_ms"]) for token in first["tokens"]] == [
        (0, 300),
        (300, 600),
    ]


def test_align_lyrics_falls_back_to_official_clock_without_agent():
    timeline = align_lyrics(
        [{"ms": 10_000, "text": "hello world"}, {"ms": 14_000, "text": "again now"}],
        "en",
        duration_ms=20_000,
        asr_words=_words(
            ("hello", 9_900, 10_400),
            ("world", 10_400, 10_900),
            ("again", 13_900, 14_400),
            ("now", 14_400, 14_900),
        ),
    )
    assert timeline["alignment_source"] == "official"
    assert [cue["text"] for cue in timeline["cues"]] == ["hello world", "again now"]


def test_align_lyrics_without_reference_still_uses_agent_rows():
    asr = _words(("la", 0, 300), ("la", 300, 600))
    timeline = align_lyrics(
        [],
        "en",
        asr_words=asr,
        sung_rows=[{"text": "la la", "from": 1, "to": 2}],
        sung_words=alignment.agent_words(asr),
    )
    assert [cue["text"] for cue in timeline["cues"]] == ["la la"]
    assert align_lyrics([], "en")["alignment"] == "empty"
