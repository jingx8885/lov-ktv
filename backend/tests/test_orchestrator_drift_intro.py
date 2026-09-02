from lovktv.pipeline.orchestrator import _align_version_drift, _prefer_asr_clock


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


def test_asr_clock_does_not_erase_long_official_lead_in():
    lines = [
        {"ms": 23_110, "text": "I saw the sun"},
        {"ms": 25_990, "text": "And felt the wind"},
        {"ms": 28_250, "text": "Blow cold"},
        {"ms": 33_820, "text": "A man learns"},
    ]
    words = [
        {"text": "I", "start_ms": 0, "end_ms": 500},
        {"text": "saw", "start_ms": 500, "end_ms": 1_000},
        {"text": "the", "start_ms": 1_000, "end_ms": 1_500},
        {"text": "sun", "start_ms": 1_500, "end_ms": 2_000},
        {"text": "And", "start_ms": 2_340, "end_ms": 2_840},
        {"text": "felt", "start_ms": 2_840, "end_ms": 3_340},
        {"text": "the", "start_ms": 3_340, "end_ms": 3_840},
        {"text": "wind", "start_ms": 3_840, "end_ms": 4_340},
        {"text": "Blow", "start_ms": 4_500, "end_ms": 5_000},
        {"text": "cold", "start_ms": 5_000, "end_ms": 5_500},
        {"text": "A", "start_ms": 6_000, "end_ms": 6_500},
        {"text": "man", "start_ms": 6_500, "end_ms": 7_000},
        {"text": "learns", "start_ms": 7_000, "end_ms": 7_500},
    ]

    assert _prefer_asr_clock(lines, words, "en", None, 20, 293_328) is None
