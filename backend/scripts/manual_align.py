"""Freeze per-song line times and lock them against Whisper realign."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from lovktv.jobs import apply_locked_manual, load_lyric_lines
from lovktv.pipeline.align import extract_envelope, vocal_regions
from lovktv.pipeline.lyrics import is_credit_lyric, write_manual_lrc

HOP = 20
SONGS = [
    "ecfeb35f67fb",
    "881e2939b7ba",
    "caf4824086bc",
    "b850f0ff8dd6",
    "6bfc0cf4afd1",
    "1b9c6a8d928a",
    "a98587441b61",
    "d1b223a131d6",
    "483cbb89ae45",
    "aa528368f87c",
]


def _energy(env: list[float], ms: int) -> float:
    if not env:
        return 0.0
    return float(env[max(0, min(len(env) - 1, ms // HOP))])


def _region_at(regions: list[tuple[int, int]], ms: int) -> tuple[int, int] | None:
    for start, end in regions:
        if start <= ms <= end and end - start >= 160:
            return start, end
    return None


def _next_attack(regions: list[tuple[int, int]], lo: int, hi: int) -> int | None:
    for start, end in regions:
        if end - start < 180:
            continue
        if lo < start < hi:
            return start
    return None


def is_title_line(text: str, ms: int) -> bool:
    body = (text or "").strip()
    if is_credit_lyric(body):
        return True
    if ms >= 800:
        return False
    lowered = body.lower()
    return any(mark in lowered for mark in ("version", "selftag", "作词", "作曲", "编曲", "制作人"))


def phrase_onsets(env: list[float], lo: int, hi: int) -> list[int]:
    """Attacks after a short dip — what an editor would click on the vocal lane."""
    if not env or hi <= lo:
        return []
    a = max(0, lo // HOP)
    b = min(len(env), max(a + 1, hi // HOP))
    chunk = env[a:b]
    if not chunk:
        return []
    peak = max(chunk) or 1.0
    high = max(70.0, peak * 0.30)
    low = max(25.0, high * 0.42)
    quiet = 0
    found: list[int] = []
    armed = True
    for index, value in enumerate(chunk):
        if value < low:
            quiet += HOP
            if quiet >= 60:
                armed = True
            continue
        if armed and value >= high:
            found.append(lo + index * HOP)
            armed = False
            quiet = 0
        else:
            quiet = 0
    return found


def pick_start(
    official: int,
    prev: int,
    nxt: int | None,
    regions: list[tuple[int, int]],
    env: list[float],
) -> int:
    """Ignore official when the vocal attack is clearly elsewhere."""
    lo = prev + 280
    hi = (nxt - 220) if nxt is not None else official + 8000
    if hi <= lo:
        return max(lo, official)
    onsets = phrase_onsets(env, max(0, lo - 200), hi + 200)
    before = [ms for ms in onsets if lo <= ms <= official]
    after_near = [ms for ms in onsets if official < ms <= min(hi, official + 500)]
    after_hole = [ms for ms in onsets if official < ms <= min(hi, official + 1600)]
    covering = _region_at(regions, official)
    if before and official - before[-1] <= 400:
        return before[-1]
    if covering is None and after_hole:
        here = _energy(env, official)
        there = _energy(env, after_hole[0] + 40)
        gap = (nxt - official) if nxt is not None else 8000
        limit = min(1600, max(400, int(gap * 0.40)))
        if after_hole[0] - official <= limit and (here < 180 or here < there * 0.45):
            return after_hole[0]
    if after_near:
        here = _energy(env, official)
        there = _energy(env, after_near[0] + 40)
        if here < there * 0.55:
            return after_near[0]
    return max(lo, official)


def decide_song(song_id: str) -> list[dict]:
    folder = ROOT / "data" / "media" / song_id
    lines = [row for row in load_lyric_lines(folder) if row.get("ms") is not None]
    env, _hop = extract_envelope(folder / "vocals.wav")
    regions = vocal_regions(env)
    chosen: list[dict] = []
    print(f"\n======== {song_id} ========")
    for index, line in enumerate(lines):
        text = str(line.get("text") or "").strip()
        official = int(line["ms"])
        if is_title_line(text, official):
            print(f"{index:02d} DROP  {official/1000:7.2f}  {text}")
            continue
        nxt = None
        for later in lines[index + 1 :]:
            later_text = str(later.get("text") or "").strip()
            later_ms = int(later["ms"])
            if not is_title_line(later_text, later_ms):
                nxt = later_ms
                break
        prev = int(chosen[-1]["start_ms"]) if chosen else max(0, official - 4000)
        start = pick_start(official, prev, nxt, regions, env)
        if chosen:
            start = max(start, int(chosen[-1]["start_ms"]) + 200)
        delta = start - official
        flag = "MOVE" if abs(delta) > 80 else "keep"
        print(f"{index:02d} {flag:4} off={official/1000:7.2f} now={start/1000:7.2f} d={delta:+5d}  {text}")
        chosen.append({"text": text, "start_ms": start})
    return chosen


if __name__ == "__main__":
    args = sys.argv[1:]
    apply = "--apply" in args
    ids = [item for item in args if not item.startswith("--")] or SONGS
    for song_id in ids:
        rows = decide_song(song_id)
        if apply:
            folder = ROOT / "data" / "media" / song_id
            write_manual_lrc(folder, rows)
            apply_locked_manual(song_id, rebuild_mtv=False)
            print(f"locked {song_id} {len(rows)} lines")
