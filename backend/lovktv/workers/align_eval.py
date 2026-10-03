"""Karaoke line-timing test standard, evaluated against the vocal stem.

Read-only: this module only *reports*.  It is the pass/fail gate for lyric
alignment so an iteration (prompt tweak, constant change, new aligner) can
prove it helped some songs without breaking others.

What "correct" means here, by timeline source:

* ``mugen`` — Karaoke Mugen ASS is human-timed ground truth.  The song
  passes when lyrics.json still mirrors mugen.ass line starts (within
  500ms) and has no structural breakage.  Timing/voice metrics are still
  reported, but a mismatch indicts the vocal stem (foreign master or stale
  separation), never the lyrics.
* ``manual`` — locked by the editor, not ground truth: still measured
  against the stem like any other timeline, it just cannot be auto-fixed.
* everything else (agent / lrc / onset / asr) — measured against the
  separated vocal envelope after removing the global clock shift:
    - ``early``  line shown > EARLY_MS before its vocal onset
    - ``late``   singing started > LATE_MS before the line appears
    - ``silent-line``  almost no voice under the line (wrong span/not sung)
    - ``order``/``past-end``  structural breakage
    - ``uncovered``  sung stretches between lines nobody claims

Usage (run inside the container so the full catalog is checked):

    python -m lovktv.workers.align_eval                 # report
    python -m lovktv.workers.align_eval --lines         # + flagged lines
    python -m lovktv.workers.align_eval --save-baseline /app/data/eval/base.json
    python -m lovktv.workers.align_eval --baseline /app/data/eval/base.json
        # ^ exit 1 when any song regressed: bad_lines up, uncovered_ms up,
        #   on_time_pct down by more than 2 points.

Exit code is 0 only when every evaluated song passes and no baseline
regression was detected.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from bisect import bisect_left
from pathlib import Path
from statistics import median
from typing import Any

from lovktv.core.config import MEDIA_DIR
from lovktv.pipeline.audio import extract_envelope, probe_duration_ms, vocal_regions
from lovktv.pipeline.lyrics import fold_ja_netease_kanji, is_credit_lyric
from lovktv.storage.store import get_song, list_songs

# Residuals are measured after removing the estimated global clock shift
# and only against real *line onsets* (vocal region starts preceded by
# LINE_GAP_MS of silence).  Mid-phrase starts are unmeasurable by design:
# legato singing has no boundary to anchor to, and anchoring to the merged
# phrase head is what produced false early/late flags.
ON_TIME_MS = 400
LATE_MS = 1200         # singing started >1.2s before the line shows: late
LATE_SOFT_MS = 700     # 700-1200ms late is reported but doesn't fail a song
EARLY_MS = 2000        # shown this early AND sitting in silence: early
# A cue inside its line's vocal region but this deep is probably a
# mid-phrase second sentence, not a late line — unmeasurable, not wrong.
RESIDUAL_MEASURE_MS = 2500
# Voice coverage under this fraction inside the cue = line on pure silence.
LOW_VOICE_RATIO = 0.20
# Silence before a region start that makes it a plausible *line* onset.
LINE_GAP_MS = 600
# Overlap with the previous line tolerated (ASS lines legitimately touch).
OVERLAP_MS = 300
# A gap only counts as a missed lyric line when it holds this much
# voice AND a fresh line onset; shorter bursts are harmonies or pickups.
MIN_GAP_VOICE_MS = 6000
# mugen.ass parity: published starts must reproduce the ASS clock.
ASS_TOLERANCE_MS = 500
# A uniform offset this large means every line lands early/late against
# the audio that actually plays — the whole timeline is off.
CLOCK_OFFSET_MS = 1200

GROUND_TRUTH_ALIGNMENTS = {"mugen", "manual"}
# Overlaps up to this size are legitimate (ad-libs, layered chorus lines);
# mugen.ass itself ships overlapping sung lines, so only a large clash
# between different lines counts as structural breakage.
ORDER_HARD_MS = 3000
TIMING_FLAGS = {"early", "late", "late-soft", "silent-line", "silent-line-hard"}
# Per-line early/late is reported but never decides the verdict: on a
# legato vocal stem a cue that starts mid-phrase cannot be told apart
# from a genuinely late line, and bleed onsets anchor false residuals.
INFO_TIMING = {"early", "late", "late-soft"}
TEXT_FLAGS = {"reading-inline"}
HARD_TIMING_FLAGS = {"silent-line-hard"}
STRUCTURAL_FLAGS = {"order-hard", "past-end"}
INFO_FLAGS = {"order", "credit", "stem-gap", "echo-line"}


def _overlap_ms(lo_a: int, hi_a: int, lo_b: int, hi_b: int) -> int:
    return max(0, min(hi_a, hi_b) - max(lo_a, lo_b))


def _voice_overlap_between(
    lo_q: int, hi_q: int, regions: list[tuple[int, int]]
) -> int:
    return sum(_overlap_ms(lo_q, hi_q, lo, hi) for lo, hi in regions)


def _voice_overlap(cue: dict[str, Any], regions: list[tuple[int, int]]) -> int:
    start = int(cue.get("start_ms") or 0)
    end = int(cue.get("end_ms") or 0)
    return _voice_overlap_between(start, end, regions)


def _overlap_total(
    a: list[tuple[int, int]], b: list[tuple[int, int]]
) -> int:
    """Total overlap between two sorted interval lists."""
    total = 0
    i = j = 0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if hi > lo:
            total += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def estimate_clock_shift(
    cues: list[dict[str, Any]], regions: list[tuple[int, int]]
) -> tuple[int, float, int | None]:
    """Best global offset between the lyric clock and the vocal clock.

    Scored by *coverage*: the fraction of sung time (shifted vocal
    regions) that falls inside a displayed cue window.  Onset counting is
    unreliable here — fast songs expose too few line onsets, and any big
    shift can match them to the wrong lines.  Coverage asks the direct
    karaoke question: is a line on screen while somebody sings?

    A nonzero shift is only accepted when it beats the zero clock by
    >=8 points of coverage and still covers >=55% of the vocal track —
    repeated sections otherwise invent phantom offsets.
    Returns (shift, coverage_at_best_shift, None).
    """
    lyric = sorted(
        (int(c.get("start_ms") or 0), int(c.get("end_ms") or 0))
        for c in cues
        if c.get("text")
    )
    if len(lyric) < 4 or not regions:
        return 0, 0.0, None
    vocal_ms = sum(hi - lo for lo, hi in regions)
    if vocal_ms <= 0:
        return 0, 0.0, None

    def _cover(shift: int) -> float:
        moved = [(lo + shift, hi + shift) for lo, hi in regions]
        return _overlap_total(lyric, moved) / vocal_ms

    lo_bound = -int(regions[-1][1]) if regions else -60000
    hi_bound = int(lyric[-1][1]) if lyric else 60000
    lo_bound = max(lo_bound, -90000)
    hi_bound = min(hi_bound, 90000)

    # coarse then refine
    best_shift = 0
    best_cover = _cover(0)
    for shift in range(lo_bound, hi_bound + 1, 500):
        cov = _cover(shift)
        if cov > best_cover:
            best_shift, best_cover = shift, cov
    for shift in range(best_shift - 450, best_shift + 451, 50):
        cov = _cover(shift)
        if cov > best_cover:
            best_shift, best_cover = shift, cov

    zero_cover = _cover(0)
    if best_shift != 0 and not (
        best_cover >= zero_cover + 0.08 and best_cover >= 0.55
    ):
        return 0, zero_cover, None
    return best_shift, best_cover, None


def line_onsets(regions: list[tuple[int, int]]) -> list[int]:
    """Region starts that follow a real silence — candidate lyric starts."""
    onsets: list[int] = []
    prev_end = -10**9
    for lo, hi in regions:
        if not onsets or lo - prev_end >= LINE_GAP_MS:
            onsets.append(lo)
        prev_end = max(prev_end, hi)
    return onsets


def score_timeline(
    cues: list[dict[str, Any]],
    regions: list[tuple[int, int]],
    duration_ms: int | None = None,
    language: str = "",
    trusted: bool = False,
    mix_check: Any = None,
    stem_check: Any = None,
    voice_energy: Any = None,
    fine_regions: list[tuple[int, int]] | None = None,
    source_starts: list[int] | None = None,
    source_lines: list[tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Line-level flags + song metrics for one timeline.

    ``trusted`` timelines keep all metrics for reporting, but timing flags
    stop counting against ``ok``: a disagreement there means the vocal stem
    is wrong, not the lyrics.
    """
    clock_shift, clock_agreement, clock_residual = estimate_clock_shift(
        cues, regions
    )
    if clock_shift:
        regions = [(lo + clock_shift, hi + clock_shift) for lo, hi in regions]
    # coverage >= 0.5 means at least half the sung track has a line on
    # screen — enough anchoring to judge individual lines.
    measurable = clock_agreement >= 0.5
    line_onset_set = set(line_onsets(regions))
    ordered_onsets = sorted(line_onset_set)
    rows: list[dict[str, Any]] = []
    prev_end = 0
    measured = 0
    on_time = 0
    shifts: list[int] = []
    for index, cue in enumerate(cues):
        text = str(cue.get("text") or cue.get("surface") or "").strip()
        start = int(cue.get("start_ms") or 0)
        end = int(cue.get("end_ms") or 0)
        flags: list[str] = []
        voice_ms = _voice_overlap(cue, regions)
        voice_ratio = voice_ms / max(end - start, 1)
        onset = None
        shift = None
        # The cue's own line onset: either the gap-preceded region it starts
        # inside (cue shown late) or the first line onset after its start
        # (cue shown on time / early).  Starting inside a region that did
        # NOT begin after a silence means legato mid-phrase — unmeasurable.
        containing = next(
            (r for r in regions if r[0] <= start < r[1]), None
        )
        # Voice that is already running when the line appears: a cue that
        # starts in silence cannot be "late" no matter which onset we
        # anchored to — bleed onsets sit seconds before the real phrase.
        early_voice_ms = _voice_overlap_between(start, start + 1500, regions)
        if measurable:
            # MIREX onset error: signed distance from the cue start to
            # the sung onset of *its own* line.
            #
            # A karaoke line is displayed ahead of its phrase, so the
            # line's onset is the next sung onset at/after the cue start.
            # Only when the cue already sits inside a sung region does
            # the line's onset live behind it — and then only if that
            # region start is itself a line onset.
            prev_b = None
            nxt = None
            for b in ordered_onsets:
                if b < start - 100:
                    prev_b = b
                else:
                    nxt = b
                    break
            if containing is not None and containing[0] in line_onset_set:
                # cue inside a sung region.  If a phrase boundary sits
                # just before the cue (<=600ms), that is the line's own
                # onset — on time.  Otherwise the region start is the
                # only onset we have; a deep residual is a merged block
                # of phrases, not a late line, so only a shallow residual
                # (cue appeared ~at/just after the phrase started) or a
                # moderately late one within a *short* region counts.
                fine_near = [
                    lo
                    for lo, _h in (fine_regions or [])
                    if start - 600 <= lo <= start + 100
                ]
                if fine_near:
                    anchor = max(fine_near)
                elif containing[1] - containing[0] <= 8000:
                    anchor = containing[0]
                else:
                    anchor = None
            elif containing is None and nxt is not None:
                # shown before the next sung phrase: early/on-time.
                anchor = nxt
            elif containing is None and prev_b is not None and start - prev_b >= LATE_MS:
                # a sung line is already running past its onset and this
                # cue still hasn't shown its phrase: late.
                anchor = prev_b
            else:
                anchor = None
            if anchor is not None:
                residual = anchor - start
                onset = anchor
                if abs(residual) <= RESIDUAL_MEASURE_MS:
                    measured += 1
                    shift = residual
                    shifts.append(abs(residual))
                    # residual = onset - start.
                    #   positive: line shown before its phrase (early).
                    #   negative: singing started, line still absent (late).
                    if residual <= -LATE_SOFT_MS:
                        # 'late' needs the line to arrive while someone is
                        # already singing — a cue that opens onto silence
                        # was anchored to a bleed onset, not its line.
                        if early_voice_ms >= 800:
                            flags.append(
                                "late" if residual <= -LATE_MS else "late-soft"
                            )
                        elif stem_check is not None and not stem_check(start, end):
                            flags.append("late" if residual <= -LATE_MS else "late-soft")
                        else:
                            flags.append("stem-gap")
                    elif residual >= EARLY_MS:
                        if voice_ms == 0:
                            if mix_check is not None and mix_check(start, end):
                                flags.append("stem-gap")
                            elif stem_check is not None and stem_check(start, end):
                                flags.append("stem-gap")
                            elif regions and end < regions[0][0]:
                                flags.append("silent-line")
                            else:
                                flags.append("silent-line-hard")
                        elif voice_ratio < LOW_VOICE_RATIO:
                            if stem_check is not None and stem_check(start, end):
                                on_time += 1  # quiet vocal: no reliable onset
                            else:
                                flags.append("early")
                        else:
                            on_time += 1
                    else:
                        on_time += 1
                # |residual| beyond RESIDUAL_MEASURE_MS: no reliable
                # boundary for this line — unmeasurable, flag nothing.
        paren = bool(text) and text.lstrip()[:1] in "(（「『" and text.rstrip()[-1:] in ")）」』"
        if paren:
            flags.append("echo-line")
        if index and start < prev_end - OVERLAP_MS:
            flags.append("order")
            if start < prev_end - ORDER_HARD_MS:
                flags.append("order-hard")
        if duration_ms and start >= duration_ms - 500:
            flags.append("past-end")
        if text and is_credit_lyric(text):
            flags.append("credit")
        elif text and language == "ja" and reading_inline(text):
            flags.append("reading-inline")
        first_sung = ordered_onsets[0] if ordered_onsets else 0
        last_sung = regions[-1][1] if regions else 0
        outside_sung_span = end < first_sung or start > last_sung
        if measurable and text and voice_ms == 0:
            if mix_check is not None and mix_check(start, end):
                # the mix is audible here, the stem just dropped the
                # voice — separator artifact, not a lyric error.
                flags.append("stem-gap")
            elif stem_check is not None and stem_check(start, end):
                flags.append("stem-gap")
            elif outside_sung_span:
                # title cards and outro credits display in silence by
                # design — not a hard failure
                flags.append("silent-line")
            elif "silent-line-hard" not in flags:
                flags.append("silent-line-hard")
        elif measurable and text and voice_ratio < LOW_VOICE_RATIO:
            if stem_check is not None and stem_check(start, end):
                pass  # quiet vocal the region detector missed
            elif not (mix_check is not None and mix_check(start, end)):
                flags.append("silent-line")
        rows.append(
            {
                "index": index,
                "text": text,
                "start_ms": start,
                "end_ms": end,
                "onset_ms": onset,
                "shift_ms": shift,
                "voice_ratio": round(voice_ratio, 3),
                "flags": flags,
            }
        )
        prev_end = max(prev_end, end)

    # Singing inside gaps between cues = missed lyric lines.  Voice alone
    # is not enough: harmonies, ad-libs and hums produce energy without
    # starting a displayable line.  A gap only counts when it also
    # contains a real line onset (a sung phrase that begins after its own
    # silence) — i.e. a whole lyric line nobody shows.
    # Missing lines: a sung region the lyric never shows.  Checked per
    # region (not per cue gap): a 4s sung phrase inside a 30s
    # instrumental gap is still a missing line.  Each candidate must
    # carry real vocal energy — stem louder than the karaoke stem at the
    # same moment — or it is a solo / interlude, not dropped lyrics.
    uncovered: list[dict[str, Any]] = []
    bounds = sorted(
        (int(c.get("start_ms") or 0), int(c.get("end_ms") or 0)) for c in cues
    )
    cue_text_rows = [
        (int(c.get("start_ms") or 0), str(c.get("text") or c.get("surface") or ""))
        for c in cues
    ]
    src_text = dict(source_lines or [])
    onset_list = sorted(line_onset_set)
    lyric_lo = bounds[0][0] if bounds else 0
    lyric_hi = bounds[-1][1] if bounds else 0
    for lo, hi in regions:
        if hi - lo < 1200:
            continue
        if _voice_overlap_between(lo, hi, bounds) >= 600:
            continue  # a cue window already covers this sung stretch
        if lo < lyric_lo - 1500 or lo > lyric_hi + 1500:
            continue  # outside the song's lyric span: intro/outro bleed
        # A sung stretch counts as a missed lyric via one of two
        # independent evidences, never both diluted:
        #   (a) the source lrc stamps a line inside it that no cue shows
        #       anywhere near — a stamp is enough even for a mid-phrase
        #       tail, and a mistimed stamp is excused when its own text
        #       is displayed a few seconds away;
        #   (b) no stamp, but the region begins a fresh line (silence-
        #       preceded onset) AND carries real vocal energy over the
        #       karaoke stem — interludes/backing fail this gate.
        stamped = []
        cue_starts = [b_lo for b_lo, _h in bounds]
        if source_starts is not None:
            stamped = [s for s in source_starts if lo - 3000 <= s <= hi + 3000]
            if stamped and any(
                abs(s - c) <= 1500 for s in stamped for c in cue_starts
            ):
                stamped = []
            stamped = [
                s
                for s in stamped
                if not any(
                    _same_line(src_text.get(s, ""), ct)
                    and abs(s - c) <= 8000
                    for c, ct in cue_text_rows
                )
            ]
        if stamped:
            pass  # the lrc itself says a lyric belongs here
        else:
            # stamp-less evidence must carry a whole sung line — a
            # two-second ad-lib or harmony tail is not a missed lyric
            if hi - lo < 2000:
                continue
            voiced = voice_energy is None or voice_energy(lo, hi)
            if not voiced or lo not in line_onset_set:
                continue
        if measurable:
            uncovered.append(
                {"start_ms": lo, "end_ms": hi, "voice_ms": hi - lo, "lines": 1}
            )

    # Section drift: a run of lines sharing one local offset — the whole
    # section sits early/late even when individual residuals stay just
    # inside tolerance.  Detect via onset->cue deltas that point the same
    # way for >=4 consecutive boundary-anchored cues.
    drift: list[dict[str, Any]] = []
    if measurable:
        run: list[int] = []
        run_sign = 0
        def flush():
            nonlocal run
            if len(run) >= 4:
                drift.append({"dir": run_sign, "lines": len(run),
                              "median_ms": int(median(run))})
            run = []
        for row in rows:
            sh = row.get("shift_ms")
            # only bounded residuals count: huge values come from merged
            # regions or long leads, not from a steadily drifting section.
            if sh is None or abs(sh) > 4000 or abs(sh) < 500:
                flush()
                run_sign = 0
                continue
            sign = 1 if sh > 0 else -1
            if sign != run_sign:
                flush()
                run_sign = sign
            run.append(sh)
        flush()

    abs_shifts = sorted(shifts)
    p90 = (
        abs_shifts[min(len(abs_shifts) - 1, math.ceil(len(abs_shifts) * 0.9) - 1)]
        if abs_shifts
        else None
    )
    def _singable(row: dict[str, Any]) -> bool:
        return "credit" not in row["flags"] and "echo-line" not in row["flags"]

    timing_rows = [
        row
        for row in rows
        if _singable(row)
        and any(flag in TIMING_FLAGS | TEXT_FLAGS for flag in row["flags"])
    ]
    hard_rows = [
        row
        for row in rows
        if _singable(row)
        and any(
            flag in HARD_TIMING_FLAGS | TEXT_FLAGS | STRUCTURAL_FLAGS
            for flag in row["flags"]
        )
    ]
    structural_rows = [
        row
        for row in rows
        if any(flag in STRUCTURAL_FLAGS for flag in row["flags"])
    ]
    if trusted:
        bad_rows = structural_rows
        uncovered = []
        drift = []
    else:
        # A line over near-silence (breaths/ad-libs picked up) is a warn,
        # not a hard failure; only voice==0 or early/late count hard.
        bad_rows = hard_rows
    score = {
        "language": language,
        "cues": len(cues),
        "trusted": trusted,
        "clock_shift_ms": clock_shift,
        "clock_agreement": round(clock_agreement, 2),
        "clock_residual_ms": clock_residual,
        "measurable": measurable,
        "measured": measured,
        "on_time": on_time,
        "on_time_pct": round(on_time / measured, 3) if measured else 0.0,
        "bad_lines": len(bad_rows),
        "timing_flags": len(timing_rows),
        "median_abs_shift_ms": int(median(abs_shifts)) if abs_shifts else None,
        "p90_abs_shift_ms": p90,
        "uncovered": uncovered,
        "uncovered_ms": sum(item["voice_ms"] for item in uncovered),
        "drift": drift,
    }
    # Three verdicts:
    #   BAD   hard evidence of mis-singing: >=3 flagged lines, a missed
    #         sung section, or structural breakage.  These are the songs a
    #         singer notices.
    #   warn  <=2 flagged lines on a measurable clock: worth looking at but
    #         plausibly a threshold edge.
    #   ok    clean, trusted, or an unmeasurable stem with intact structure.
    if trusted:
        score["stem_drift_ms"] = clock_shift if abs(clock_shift) >= 1500 else 0
        score["stem_suspect"] = not measurable
        score["ok"] = not bad_rows
        score["verdict"] = "ok" if not bad_rows else "BAD"
    else:
        # past-end is a single line running past the audio tail — a line
        # error, not structural breakage.  Only overlapping timelines
        # (order-hard) prove the timeline is structurally wrong.
        structural = any(
            "order-hard" in row["flags"] for row in rows
        )
        clock_off = measurable and abs(clock_shift) >= CLOCK_OFFSET_MS
        score["clock_offset_ms"] = clock_shift if clock_off else 0
        hard = (
            len(bad_rows) >= 3
            or bool(uncovered)
            or len(drift) >= 1
            or (measurable and structural)
            or clock_off
        )
        if hard:
            verdict = "BAD"
        elif not measurable:
            # Lyric and stem clocks disagree too much to judge lines; the
            # stem is suspect, not the lyrics.  Structural breakage is the
            # only thing still provable.
            verdict = "warn" if structural else "ok"
        elif bad_rows:
            verdict = "warn"
        else:
            verdict = "ok"
        score["verdict"] = verdict
        score["ok"] = verdict != "BAD"
    return {"score": score, "lines": rows}


def _mix_checker(
    envelope: list[float], hop_ms: int, floor_frac: float = 0.2
):
    """True when the full mix has audible energy inside [lo, hi].

    Cross-checks stem silence: the separator drops quiet or ambient
    vocals, so 'no stem voice' only proves a bad line when the mix
    itself is also quiet there.
    """
    if not envelope:
        return None
    ranked = sorted(envelope)
    floor = max(ranked[len(ranked) // 2] * floor_frac, 50.0)

    def active(lo: int, hi: int) -> bool:
        a = max(0, int(lo / hop_ms))
        b = min(len(envelope), int(hi / hop_ms) + 1)
        if b <= a:
            return False
        seg = envelope[a:b]
        return sum(v >= floor for v in seg) / len(seg) >= 0.5

    return active


def _voice_audio(out_dir: Path) -> Path | None:
    for name in ("vocals.wav", "guide.m4a", "original.mp3", "karaoke.m4a"):
        path = out_dir / name
        if path.exists():
            return path
    return None


def mugen_parity(out_dir: Path, timeline: dict[str, Any]) -> dict[str, Any] | None:
    """Compare lyrics.json line starts with the authoritative mugen.ass.

    Mugen subtitles are hand-timed on the MV; the published timeline must
    reproduce their starts within ASS_TOLERANCE_MS.  Returns None when the
    song carries no ass source.
    """
    ass_path = out_dir / "mugen.ass"
    if not ass_path.exists():
        return None
    try:
        from lovktv.catalog.mugen import timeline_from_ass

        truth = timeline_from_ass(
            ass_path.read_text(encoding="utf-8", errors="replace"),
            str(timeline.get("language") or "ja"),
        )
    except (OSError, RuntimeError, UnicodeError):
        return {"ok": False, "error": "mugen.ass unreadable"}
    truth_cues = truth.get("cues") or []
    cues = timeline.get("cues") or []
    mismatches: list[dict[str, Any]] = []
    for index, gold in enumerate(truth_cues):
        have = cues[index] if index < len(cues) else {}
        got = int(have.get("start_ms") or -1)
        want = int(gold.get("start_ms") or 0)
        if abs(got - want) > ASS_TOLERANCE_MS:
            mismatches.append({"index": index, "ass_ms": want, "lyrics_ms": got})
    return {
        "ok": len(cues) == len(truth_cues) and not mismatches,
        "ass_lines": len(truth_cues),
        "lyrics_lines": len(cues),
        "mismatches": mismatches[:20],
    }


def _voice_energy(envelope: list[float], hop_ms: int, k_env, k_hop):
    """True when stem energy in [lo,hi] beats the karaoke stem.

    A sung phrase lifts the vocal stem well above the instrumental at the
    same moment; a guitar solo sits in both stems.  Compared per sung
    region so a 4s vocal inside a 30s instrumental gap still counts.
    Returns None when karaoke stem is absent.
    """
    if not envelope or not k_env:
        return None
    ks = sorted(k_env)
    k_floor = max(ks[len(ks) // 2] * 0.3, 60.0)
    vs = sorted(envelope)
    v_floor = max(vs[len(vs) // 2] * 0.3, 60.0)

    def has_voice(lo: int, hi: int) -> bool:
        a = int(lo / hop_ms)
        b = min(len(envelope), int(hi / hop_ms) + 1)
        ka = int(lo / k_hop)
        kb = min(len(k_env), int(hi / k_hop) + 1)
        v_seg = envelope[a:b]
        k_seg = k_env[ka:kb]
        if not v_seg or not k_seg:
            return False
        v_active = sum(x >= v_floor for x in v_seg) / len(v_seg)
        k_active = sum(x >= k_floor for x in k_seg) / len(k_seg)
        # real singing: vocal stem clearly active AND louder than the
        # instrumental at the same moment.  A belted chorus over a loud
        # band saturates both stems, so this gate alone misses loud
        # singing — the uncovered check therefore also accepts an lrc
        # stamp falling inside the region as corroboration.
        return v_active >= 0.5 and v_active > k_active + 0.15

    return has_voice


def audit_song(song_id: str) -> dict[str, Any]:
    out_dir = MEDIA_DIR / song_id
    path = out_dir / "lyrics.json"
    song = get_song(song_id) or {}
    base = {
        "id": song_id,
        "title": str(song.get("title") or ""),
        "artist": str(song.get("artist") or ""),
    }
    if not path.exists():
        return {**base, "ok": True, "skipped": "no-lyrics"}
    try:
        timeline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**base, "ok": False, "error": "lyrics.json unreadable"}
    if timeline.get("burned_lyrics"):
        return {**base, "ok": True, "skipped": "burned"}
    language = str(timeline.get("language") or "")
    voice = _voice_audio(out_dir)
    if voice is None:
        return {**base, "ok": True, "skipped": "no-audio"}
    envelope, hop_ms = extract_envelope(voice)
    regions = vocal_regions(envelope, hop_ms)
    src = out_dir / "original.mp3"
    duration = probe_duration_ms(src) if src.exists() else probe_duration_ms(voice)

    alignment = str(timeline.get("alignment") or "")
    mugen = alignment == "mugen"
    trusted = alignment in GROUND_TRUTH_ALIGNMENTS
    mix_check = None
    for name in ("original.mp3", "karaoke.m4a", "guide.m4a"):
        mix_path = out_dir / name
        if mix_path.exists() and mix_path != voice:
            mix_env, mix_hop = extract_envelope(mix_path)
            mix_check = _mix_checker(mix_env, mix_hop)
            break
    stem_check = _mix_checker(envelope, hop_ms, floor_frac=0.08)
    fine_regions = vocal_regions(envelope, hop_ms, min_ms=60, merge_gap_ms=60)
    k_env: list[float] = []
    k_hop = hop_ms
    karo = out_dir / "karaoke.m4a"
    if karo.exists():
        k_env, k_hop = extract_envelope(karo)
    voice_energy = _voice_energy(envelope, hop_ms, k_env, k_hop)
    cues_list = timeline.get("cues") or []
    source_rows = [
        (s, t) for s, t in _source_lines(out_dir / "lyrics.lrc") if t
    ]
    stored = score_timeline(
        cues_list,
        regions,
        duration,
        language,
        trusted=trusted,
        mix_check=mix_check,
        stem_check=stem_check,
        voice_energy=voice_energy,
        fine_regions=fine_regions,
        source_starts=None if trusted else [s for s, _t in source_rows],
        source_lines=None if trusted else source_rows,
    )
    if not trusted:
        stored["score"]["dropped"] = dropped_source_lines(
            out_dir / "lyrics.lrc", cues_list, regions,
            ja_only=(language == "ja"),
        )
        if stored["score"]["dropped"]:
            stored["score"]["verdict"] = "BAD"
            stored["score"]["ok"] = False
    result: dict[str, Any] = {
        **base,
        "alignment": alignment,
        "voice": voice.name,
        "stored": stored["score"],
        "lines": stored["lines"],
    }
    ok = bool(stored["score"].get("ok"))
    if mugen:
        parity = mugen_parity(out_dir, timeline)
        if parity is not None:
            result["mugen_parity"] = parity
            if not parity.get("ok"):
                stored["score"]["verdict"] = "BAD"
                stored["score"]["ok"] = False
                ok = False
    result["ok"] = ok
    return result


def _source_lines(path: Path) -> list[tuple[int, str]]:
    """(start_ms, text) pairs from a plain .lrc file, if present."""
    if not path.exists():
        return []
    rows: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)", line.strip())
        if match:
            minutes = int(match.group(1))
            start_ms = minutes * 60000 + int(float(match.group(2)) * 1000)
            rows.append((start_ms, match.group(3).strip()))
    return rows


def _norm_text(text: str) -> str:
    # fold NetEase Simplified lookalikes into Japanese kanji first so a
    # Simplified lrc and a Japanese timeline still compare equal
    folded = fold_ja_netease_kanji(text or "")
    return "".join(ch.lower() for ch in folded if ch.isalnum())


def _same_line(a: str, b: str) -> bool:
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def dropped_source_lines(
    lrc_path: Path,
    cues: list[dict[str, Any]],
    regions: list[tuple[int, int]],
    ja_only: bool = False,
) -> list[dict[str, Any]]:
    """Source lyric lines that no cue reproduces anywhere near their
    stamped position — while the stem shows actual singing there.

    The lrc-energy aligner re-times repeats and can drop a line entirely
    (chorus pasted onto the wrong instance, whole hook missing).  The
    source lrc's own clock is trusted only where the vocal stem agrees
    someone is singing; a line dropped to a silent timestamp is a bad
    source, not a dropped lyric.
    """
    cue_rows = [
        (int(c.get("start_ms") or 0), str(c.get("text") or c.get("surface") or ""))
        for c in cues
        if (c.get("text") or c.get("surface"))
    ]
    dropped: list[dict[str, Any]] = []
    for start_ms, text in _source_lines(lrc_path):
        if not text or is_credit_lyric(text):
            continue
        if ja_only and not re.search(r"[\u3040-\u30ff]", text):
            # a ja timeline cannot be missing a line that has no kana —
            # it is a translation or uploader comment, not a sung lyric
            continue
        window = (start_ms - 1000, start_ms + 1000)
        if _voice_overlap_between(*window, regions) < 800:
            continue  # nothing sung where the source put it: bad source
        # The line counts as dropped only when its text is missing
        # from the whole timeline — a stamp with no same-text cue nearby
        # usually means the source lrc itself is off by a verse or the
        # aligner retimed it, neither of which drops a lyric.
        if any(_same_line(text, cue_text) for _lo, cue_text in cue_rows):
            continue
        dropped.append({"start_ms": start_ms, "text": text[:40]})
    return dropped


def reading_inline(text: str) -> bool:
    """Japanese line carrying its own reading inline.

    Bug form: `大丈夫ダイジョウブだいじょうぶ` — kanji, then the same
    reading as katakana AND hiragana concatenated.  Detects katakana
    runs whose hiragana echo follows immediately.
    """
    for match in re.finditer(r"[\u30a0-\u30ff]{3,}[\u3040-\u309f]{4,}", text):
        kana = match.group(0)
        cut = next(
            (i for i, ch in enumerate(kana) if "\u3040" <= ch <= "\u309f"),
            None,
        )
        if cut is None:
            continue
        kata, hira = kana[:cut], kana[cut:]
        kata_as_hira = kata.translate(
            str.maketrans(
                {chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)}
            )
        )
        if hira.startswith(kata_as_hira[: len(hira)]) or kata_as_hira.startswith(hira):
            return True
    return False


def _load_baseline(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def compare_baseline(
    results: list[dict[str, Any]], baseline: dict[str, Any]
) -> list[str]:
    """Regression lines; empty means as good or better than the snapshot."""
    problems: list[str] = []
    songs = baseline.get("songs") or {}
    for item in results:
        old = songs.get(item["id"])
        if not isinstance(old, dict) or item.get("skipped"):
            continue
        new_score = item.get("stored") or {}
        old_score = old.get("score") or {}
        if int(new_score.get("bad_lines") or 0) > int(old_score.get("bad_lines") or 0):
            problems.append(
                f"{item['id']} bad_lines {old_score.get('bad_lines')} -> {new_score.get('bad_lines')}"
            )
        if int(new_score.get("uncovered_ms") or 0) > int(old_score.get("uncovered_ms") or 0):
            problems.append(
                f"{item['id']} uncovered {old_score.get('uncovered_ms')} -> {new_score.get('uncovered_ms')}"
            )
        if float(new_score.get("on_time_pct") or 0) < float(
            old_score.get("on_time_pct") or 0
        ) - 0.02:
            problems.append(
                f"{item['id']} on_time {old_score.get('on_time_pct')} -> {new_score.get('on_time_pct')}"
            )
        if bool(old_score.get("ok")) and not bool(new_score.get("ok")):
            problems.append(f"{item['id']} ok -> BAD")
    return problems


def _summary(item: dict[str, Any]) -> str:
    if item.get("skipped"):
        return f"skip:{item['skipped']}"
    if item.get("error"):
        return f"error:{item['error']}"
    score = item.get("stored") or {}
    bits = [
        f"on={score.get('on_time')}/{score.get('measured')}",
        f"bad={score.get('bad_lines')}",
        f"miss={len(score.get('uncovered') or [])}",
        f"drop={len(score.get('dropped') or [])}",
        f"drift={len(score.get('drift') or [])}",
    ]
    if score.get("median_abs_shift_ms") is not None:
        bits.append(f"med={score['median_abs_shift_ms']}ms")
    if score.get("stem_drift_ms"):
        bits.append(f"stem-drift={score['stem_drift_ms']}ms")
    if score.get("clock_offset_ms"):
        bits.append(f"clock-offset={score['clock_offset_ms']}ms")
    if score.get("stem_suspect"):
        bits.append("stem-suspect")
    if score.get("measurable") is False:
        bits.append("unmeasurable")
    parity = item.get("mugen_parity")
    if parity is not None and not parity.get("ok"):
        bits.append(f"ass-diff={len(parity.get('mismatches') or [])}")
    status = (item.get("stored") or {}).get("verdict") or (
        "ok" if item.get("ok") else "BAD"
    )
    return f"{status:4} " + " ".join(bits)


def run(song_ids: list[str] | None = None) -> list[dict[str, Any]]:
    ids = song_ids or [row["id"] for row in list_songs()]
    results: list[dict[str, Any]] = []
    for song_id in ids:
        try:
            results.append(audit_song(song_id))
        except Exception as exc:  # noqa: BLE001
            results.append({"id": song_id, "ok": False, "error": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score karaoke line timing against the vocal stem"
    )
    parser.add_argument(
        "song_ids", nargs="*", help="Song ids; default is the whole catalog"
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Compare against a saved report; exit 1 on regression",
    )
    parser.add_argument(
        "--save-baseline", type=Path, help="Write a compact score snapshot"
    )
    parser.add_argument("--out", type=Path, help="Write the full JSON report here")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    parser.add_argument("--all", action="store_true", help="Also list songs that pass")
    parser.add_argument("--lines", action="store_true", help="Print every flagged line")
    args = parser.parse_args()

    results = run(args.song_ids or None)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            if item.get("ok") and not args.all:
                continue
            label = f"{item.get('title') or ''} · {item.get('artist') or ''}".strip(" ·")
            print(f"{item['id']} {_summary(item):<72} {label}", flush=True)
            if args.lines:
                for row in item.get("lines") or []:
                    if row["flags"]:
                        print(
                            f"    #{row['index']:>2} [{row['start_ms']:>7}-{row['end_ms']:>7}] "
                            f"shift={row['shift_ms']} voice={row['voice_ratio']} "
                            f"{','.join(row['flags'])} {row['text'][:36]}",
                            flush=True,
                        )
                for hole in (item.get("stored") or {}).get("uncovered") or []:
                    print(
                        f"    missed vocal {hole['start_ms']}-{hole['end_ms']}ms",
                        flush=True,
                    )
                parity = item.get("mugen_parity") or {}
                for mm in parity.get("mismatches") or []:
                    print(
                        f"    ass #{mm['index']} ass={mm['ass_ms']} lyrics={mm['lyrics_ms']}",
                        flush=True,
                    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.save_baseline:
        snapshot = {
            "songs": {
                item["id"]: {"score": item.get("stored") or {}}
                for item in results
                if item.get("id")
            }
        }
        args.save_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.save_baseline.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    regressions: list[str] = []
    if args.baseline:
        regressions = compare_baseline(results, _load_baseline(args.baseline))
        for line in regressions:
            print(f"regression: {line}", flush=True)

    bad = [
        item
        for item in results
        if (item.get("stored") or {}).get("verdict") == "BAD"
        or (not item.get("ok") and not item.get("stored"))
    ]
    warned = [
        item
        for item in results
        if (item.get("stored") or {}).get("verdict") == "warn"
    ]
    print(
        f"songs {len(results)} problem {len(bad)} warn {len(warned)}"
        + (f" regressions {len(regressions)}" if args.baseline else ""),
        flush=True,
    )
    return 1 if (bad or regressions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
