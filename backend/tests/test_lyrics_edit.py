from lovktv.pipeline.align import pack_tokens_to_singing
from lovktv.pipeline.lyrics import rebuild_manual_timeline, shift_cues, validate_timeline


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


def test_manual_timeline_holds_until_next_line():
    existing = {
        "language": "en",
        "cues": [
            {
                "text": "Get along Try again",
                "start_ms": 86300,
                "end_ms": 90810,
                "tokens": [
                    {"text": "Get", "start_ms": 86300, "end_ms": 87400, "reading": ""},
                    {"text": "along", "start_ms": 87400, "end_ms": 90810, "reading": ""},
                ],
            },
            {
                "text": "next",
                "start_ms": 94210,
                "end_ms": 97000,
                "tokens": [{"text": "next", "start_ms": 94210, "end_ms": 97000, "reading": ""}],
            },
        ],
    }
    out = rebuild_manual_timeline(
        [
            {"text": "Get along Try again", "ms": 86300},
            {"text": "next", "ms": 94210},
        ],
        existing,
    )
    assert out["alignment_source"] == "manual"
    assert out["cues"][0]["end_ms"] == 94210
    assert out["cues"][0]["tokens"][0]["text"] == "Get"


def test_pack_tokens_sweeps_voice_not_hold():
    hop = 20
    env = [20.0] * (86300 // hop) + [800.0] * ((90800 - 86300) // hop) + [10.0] * 300
    cues = [
        {
            "text": "Get along Try again",
            "start_ms": 86300,
            "end_ms": 94210,
            "tokens": [
                {"text": "Get", "start_ms": 86300, "end_ms": 88200, "reading": ""},
                {"text": "along", "start_ms": 88200, "end_ms": 90200, "reading": ""},
                {"text": "Try", "start_ms": 90200, "end_ms": 92200, "reading": ""},
                {"text": "again", "start_ms": 92200, "end_ms": 94210, "reading": ""},
            ],
        }
    ]
    pack_tokens_to_singing(cues, env, hop)
    assert cues[0]["end_ms"] == 94210
    assert cues[0]["sing_end_ms"] <= 91000
    assert cues[0]["tokens"][-1]["end_ms"] == cues[0]["sing_end_ms"]
    assert cues[0]["tokens"][-1]["end_ms"] < 94210


def test_validate_timeline_rejects_empty():
    try:
        validate_timeline({"cues": []})
    except ValueError as exc:
        assert "没有歌词" in str(exc)
    else:
        raise AssertionError("expected empty cues to fail")
