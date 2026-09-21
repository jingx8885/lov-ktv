/**
 * Classic karaoke pairing: even cues sit on the left, odd cues on the right.
 * After a row finishes it is replaced by the next cue of the same side.
 *
 * @param {LyricCue[] | null | undefined} cues
 * @param {number} t
 */
export function karaokePair(cues, t) {
  const list = cues || [];
  if (!list.length) {
    return { left: null, right: null, leftTime: -1, rightTime: -1, liveIndex: -1 };
  }
  const clock = Math.round(Number(t) || 0);
  const live = list.findIndex((cue) => clock >= cue.start_ms && clock < cue.end_ms);
  const upcoming = list.findIndex((cue) => clock < cue.start_ms);
  let focus = live;
  if (focus < 0) {
    if (upcoming === 0) focus = 0;
    else if (upcoming > 0) focus = upcoming - 1;
    else focus = list.length - 1;
  }

  /** @param {0 | 1} parity */
  function slotIndex(parity) {
    if (focus % 2 === parity) return focus;
    const next = focus + 1;
    if (next < list.length && next % 2 === parity) return next;
    const prev = focus - 1;
    if (prev >= 0 && prev % 2 === parity) return prev;
    return -1;
  }

  /** @param {number} index */
  function timeFor(index) {
    if (index < 0) return -1;
    if (live === index) return clock;
    if (clock >= list[index].end_ms) return 1e12;
    return -1;
  }

  const leftIndex = slotIndex(0);
  const rightIndex = slotIndex(1);
  return {
    left: leftIndex >= 0 ? list[leftIndex] : null,
    right: rightIndex >= 0 ? list[rightIndex] : null,
    leftTime: timeFor(leftIndex),
    rightTime: timeFor(rightIndex),
    liveIndex: live
  };
}
