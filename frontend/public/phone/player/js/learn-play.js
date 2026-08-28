import { $ } from "../../../shared/ui/js/dom.js";
import { state } from "../../state.js";
import { applyPlayerVocalMix, hookPlayerAudio, pausePlayerTracks, syncGuide } from "./playback.js";

export const LEARN_DIFFS = {
  easy: { id: "easy", rate: 0.8 },
  normal: { id: "normal", rate: 1 },
  hard: { id: "hard", rate: 1.25 },
};

const DIFF_KEY = "lovktv-learn-diff";
let playGen = 0;
let diffId = "normal";

export function getLearnDiff() {
  return LEARN_DIFFS[diffId] ? diffId : "normal";
}

export function getLearnRate() {
  return LEARN_DIFFS[getLearnDiff()].rate;
}

export function applyLearnRate() {
  const rate = getLearnRate();
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  if (audio) audio.playbackRate = rate;
  if (guide) guide.playbackRate = rate;
}

export function resetLearnRate() {
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  if (audio) audio.playbackRate = 1;
  if (guide) guide.playbackRate = 1;
}

export function setLearnDiff(id) {
  diffId = LEARN_DIFFS[id] ? id : "normal";
  try { localStorage.setItem(DIFF_KEY, diffId); } catch (err) {}
  applyLearnRate();
  return getLearnDiff();
}

export function loadLearnDiff() {
  try {
    const saved = localStorage.getItem(DIFF_KEY);
    if (LEARN_DIFFS[saved]) diffId = saved;
  } catch (err) {}
  applyLearnRate();
  return getLearnDiff();
}

/** @param {number} startMs @param {number} endMs @param {{ vocal?: boolean }} [opts] */
export function playCueWindow(startMs, endMs, opts) {
  const gen = ++playGen;
  const audio = $("playerAudio");
  if (!audio) return Promise.resolve(false);
  if (opts && opts.vocal != null) {
    state.playerVocal = opts.vocal ? 1 : 0;
    applyPlayerVocalMix();
  }
  return new Promise((resolve) => {
    const start = Math.max(0, Number(startMs) || 0) / 1000;
    const stop = Math.max(start + 0.18, (Number(endMs) || 0) / 1000);
    const tick = () => {
      if (gen !== playGen) {
        resolve(false);
        return;
      }
      const now = audio.currentTime || 0;
      if (now >= stop - 0.03 || audio.ended) {
        pausePlayerTracks();
        resolve(true);
        return;
      }
      requestAnimationFrame(tick);
    };
    hookPlayerAudio();
    applyLearnRate();
    try { audio.currentTime = start; } catch (err) {}
    syncGuide(start);
    state.playerHeld = false;
    audio.play().then(() => {
      applyPlayerVocalMix();
      requestAnimationFrame(tick);
    }).catch(() => resolve(false));
  });
}

export function cancelCueWindow() {
  playGen += 1;
  pausePlayerTracks();
}
