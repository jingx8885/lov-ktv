from lovktv.pipeline.orchestrator import _align_version_drift


def test_version_drift_does_not_project_past_unmatched_intro():
    """A spoken intro must not move the first lyric line to 0 ms."""
    lines = [
        {"ms": 15_770, "text": "I think about that day"},
        {"ms": 17_570, "text": "I left him at a Greyhound station"},
        {"ms": 19_560, "text": "West of Sante Fe"},
        {"ms": 21_260, "text": "We were seventeen"},
    ]
    asr_words = [
        {"text": "I", "start_ms": 58_000, "end_ms": 58_300},
        {"text": "left", "start_ms": 58_300, "end_ms": 58_700},
        {"text": "him", "start_ms": 58_700, "end_ms": 59_000},
        {"text": "summer", "start_ms": 60_900, "end_ms": 61_820},
        {"text": "Sunday", "start_ms": 61_820, "end_ms": 62_360},
        {"text": "nights", "start_ms": 62_360, "end_ms": 62_880},
        {"text": "West", "start_ms": 63_000, "end_ms": 63_400},
        {"text": "of", "start_ms": 63_400, "end_ms": 63_700},
        {"text": "Sante", "start_ms": 63_700, "end_ms": 64_080},
        {"text": "We", "start_ms": 65_000, "end_ms": 65_300},
        {"text": "were", "start_ms": 65_300, "end_ms": 65_700},
    ]
    matches = [
        {"lyric": 2, "from": 1, "to": 3},
        {"lyric": 3, "from": 7, "to": 9},
        {"lyric": 4, "from": 10, "to": 11},
    ]

    assert _align_version_drift(lines, asr_words, "en", matches, 256_584) is None
