from lovktv.workers.align_eval import estimate_clock_shift, mugen_parity, score_timeline


def _regions(specs):
    return [(lo, hi) for lo, hi in specs]


def _cues(specs):
    return [
        {
            "text": text,
            "start_ms": start,
            "end_ms": end,
            "tokens": [{"text": text, "start_ms": start, "end_ms": end}],
        }
        for start, end, text in specs
    ]


def test_clock_shift_recovers_offset_timeline():
    regions = _regions([(10500, 14000), (20500, 24000), (30500, 34000), (40500, 44000)])
    cues = _cues(
        [
            (10400, 13500, "a"),
            (20400, 23500, "b"),
            (30400, 33500, "c"),
            (40400, 43500, "d"),
        ]
    )
    shift, agreement, _residual = estimate_clock_shift(cues, regions)
    assert agreement >= 0.8
    assert abs(shift) <= 700
    report = score_timeline(cues, regions)
    assert report["score"]["ok"]
    assert report["score"]["on_time"] == 4


def test_clock_shift_handles_foreign_master():
    regions = _regions(
        [(19000, 22000), (29000, 32000), (39000, 42000), (49000, 52000)]
    )
    cues = _cues(
        [
            (5000, 8000, "a"),
            (15000, 18000, "b"),
            (25000, 28000, "c"),
            (35000, 38000, "d"),
        ]
    )
    _shift, agreement, _residual = estimate_clock_shift(cues, regions)
    assert agreement >= 0.5
    report = score_timeline(cues, regions)
    assert abs(report["score"]["clock_shift_ms"]) >= 13000


def test_score_flags_late_and_silent_lines():
    regions = _regions(
        [(10000, 14000), (20100, 24000), (30000, 34000), (40000, 44000)]
    )
    cues = _cues(
        [
            (10100, 14000, "a"),
            (21800, 24000, "b"),      # starts 1.7s after its onset: late
            (30100, 34000, "b2"),
            (40100, 44000, "d"),      # covers the last sung region
            (45000, 48000, "c"),      # outro silence: soft flag only
        ]
    )
    report = score_timeline(cues, regions)
    flags = {row["index"]: row["flags"] for row in report["lines"]}
    assert "late" in flags[1]
    assert "silent-line" in flags[4]
    assert "silent-line-hard" not in flags[4]
    assert report["score"]["verdict"] == "ok"


def test_uncovered_voice_between_cues():
    regions = _regions(
        [(10000, 14000), (20000, 26000), (30000, 34000), (40000, 44000), (50000, 54000)]
    )
    cues = _cues(
        [
            (10000, 14000, "a"),
            (30000, 34000, "c"),
            (40000, 44000, "d"),
            (50000, 54000, "e"),
        ]
    )
    report = score_timeline(cues, regions)
    uncovered = report["score"]["uncovered"]
    assert any(u["start_ms"] <= 20000 and u["end_ms"] >= 26000 for u in uncovered)


def test_mid_phrase_start_is_not_flagged():
    # Cue starts inside a long sung region: residual to the region start is
    # big, but the cue sits on voice so it must stay unflagged.
    regions = _regions([(10000, 20000), (21000, 24000), (30000, 34000), (40000, 44000)])
    cues = _cues(
        [(14000, 20000, "a"), (21000, 24000, "b"), (30000, 34000, "c"), (40000, 44000, "d")]
    )
    report = score_timeline(cues, regions)
    assert not any("late" in row["flags"] for row in report["lines"])


def test_trusted_timeline_reports_but_passes():
    # Mugen-style: stem on a foreign clock produces late/silent evidence,
    # but the timeline itself still passes and records stem drift instead.
    regions = _regions([(24000, 28000), (34000, 38000), (44000, 48000), (54000, 58000)])
    cues = _cues(
        [
            (10100, 14000, "a"),
            (20100, 24000, "b"),
            (30100, 34000, "c"),
            (40100, 44000, "d"),
        ]
    )
    report = score_timeline(cues, regions, trusted=True)
    score = report["score"]
    assert score["ok"]
    assert score["stem_drift_ms"] != 0 or score["stem_suspect"]
    assert score["timing_flags"] == 0 or score["bad_lines"] == 0


def test_trusted_still_fails_on_structure():
    regions = _regions([(10000, 14000), (20000, 24000), (30000, 34000), (40000, 44000)])
    cues = _cues(
        [
            (10100, 14000, "a"),
            (20100, 24000, "b"),
            (20500, 25000, "overlap!"),
            (40100, 44000, "d"),
        ]
    )
    report = score_timeline(cues, regions, trusted=True)
    assert not report["score"]["ok"]


def test_reading_inline_detects_kana_echo():
    from lovktv.workers.align_eval import reading_inline

    assert reading_inline("大丈夫ダイジョウブだいじょうぶ")
    assert not reading_inline("奇跡だって起こせる")
    assert not reading_inline("It is all right")
    assert not reading_inline("パソコンがおかしい")


def test_dropped_source_lines_flags_missing_hook(tmp_path):
    from lovktv.workers.align_eval import dropped_source_lines

    lrc = tmp_path / "lyrics.lrc"
    lrc.write_text(
        "[00:08.10]line one\n[00:13.40]hook that was dropped\n"
        "[00:20.00]line three\n",
        encoding="utf-8",
    )
    cues = [
        {"start_ms": 8100, "end_ms": 10080, "text": "line one"},
        {"start_ms": 20000, "end_ms": 23000, "text": "line three"},
    ]
    regions = [(8000, 11000), (13000, 16000), (19800, 23200)]
    dropped = dropped_source_lines(lrc, cues, regions)
    assert len(dropped) == 1
    assert dropped[0]["start_ms"] == 13400


def test_dropped_source_lines_ignores_bad_source(tmp_path):
    from lovktv.workers.align_eval import dropped_source_lines

    lrc = tmp_path / "lyrics.lrc"
    lrc.write_text("[00:08.00]line one\n[00:50.00]sung nowhere here\n", encoding="utf-8")
    cues = [{"start_ms": 8100, "end_ms": 10080, "text": "line one"}]
    regions = [(8000, 11000)]
    assert dropped_source_lines(lrc, cues, regions) == []


def test_silent_line_hard_inside_sung_span():
    regions = _regions([(10000, 14000), (20000, 24000), (40000, 44000)])
    cues = _cues(
        [
            (10100, 14000, "a"),
            (20100, 24000, "b"),
            (25000, 30000, "ghost"),  # silence mid-song: hard
            (40100, 44000, "d"),
        ]
    )
    report = score_timeline(cues, regions)
    flags = {row["index"]: row["flags"] for row in report["lines"]}
    assert "silent-line-hard" in flags[2]
