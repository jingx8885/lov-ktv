from lovktv.pipeline.lyrics import shift_cues, validate_timeline


def test_shift_one_line_keeps_neighbors():
    cues = [
        {"text": "a", "start_ms": 1000, "end_ms": 2000, "tokens": [{"text": "a", "start_ms": 1000, "end_ms": 2000, "reading": ""}]},
        {"text": "b", "start_ms": 2000, "end_ms": 3000, "tokens": [{"text": "b", "start_ms": 2000, "end_ms": 3000, "reading": ""}]},
        {"text": "c", "start_ms": 3000, "end_ms": 4000, "tokens": [{"text": "c", "start_ms": 3000, "end_ms": 4000, "reading": ""}]},
    ]
    out = shift_cues(cues, 1, 200)
    assert out[0]["start_ms"] == 1000
    assert out[1]["start_ms"] == 2200
    assert out[1]["tokens"][0]["start_ms"] == 2200
    assert out[2]["start_ms"] == 3000


def test_shift_rest_moves_later_lines():
    cues = [
        {"text": "a", "start_ms": 1000, "end_ms": 2000, "tokens": [{"text": "a", "start_ms": 1000, "end_ms": 2000}]},
        {"text": "b", "start_ms": 2000, "end_ms": 3000, "tokens": [{"text": "b", "start_ms": 2000, "end_ms": 3000}]},
        {"text": "c", "start_ms": 3000, "end_ms": 4000, "tokens": [{"text": "c", "start_ms": 3000, "end_ms": 4000}]},
    ]
    out = shift_cues(cues, 1, -200, rest=True)
    assert out[1]["start_ms"] == 1800
    assert out[2]["start_ms"] == 2800
    assert out[0]["end_ms"] <= out[1]["start_ms"]


def test_validate_timeline_rejects_empty():
    try:
        validate_timeline({"cues": []})
    except ValueError as exc:
        assert "没有歌词" in str(exc)
    else:
        raise AssertionError("expected empty cues to fail")
