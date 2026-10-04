from lovktv.pipeline.bounds import line_sing_end
from lovktv.workers.lyric_fill import early_fill_cues


def _cue(start, end, last_token_end):
    return {
        "text": "line",
        "start_ms": start,
        "end_ms": end,
        "tokens": [
            {"text": "a", "start_ms": start, "end_ms": start + 100},
            {"text": "b", "start_ms": start + 100, "end_ms": last_token_end},
        ],
    }


def test_early_fill_flags_stale_pack():
    # Vocal phrase runs 23.98s-33.20s but the stored sweep dies 850ms in,
    # exactly the legacy-fragment bug seen in production lyrics.json.
    regions = [(14200, 23380), (23980, 33200)]
    cues = [_cue(23890, 30400, 24740)]
    assert line_sing_end(23890, 30400, regions) == 30400
    assert early_fill_cues(cues, regions) == [0]


def test_early_fill_ignores_lines_already_on_the_phrase():
    regions = [(14200, 23380), (23980, 33200)]
    cues = [_cue(23890, 30400, 30100)]
    assert early_fill_cues(cues, regions) == []


def test_early_fill_ignores_cues_without_tokens():
    regions = [(14200, 23380), (23980, 33200)]
    cues = [{"text": "line", "start_ms": 23890, "end_ms": 30400, "tokens": []}]
    assert early_fill_cues(cues, regions) == []


def test_early_fill_respects_the_gap_threshold():
    regions = [(23890, 30000)]
    # Stored sweep ends 400ms before the measured sing_end: normal short
    # breath, not a stale pack.
    cues = [_cue(23890, 30400, 29600)]
    assert early_fill_cues(cues, regions) == []
