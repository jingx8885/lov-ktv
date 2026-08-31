import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import {
  applyPlayerVocalMix,
  hookPlayerAudio,
  pausePlayerTracks,
  switchPlayerTrack,
  syncGuide
} from "../playback/controls.js";

/** @param {string | HTMLElement | null | undefined} id */
function node(id) {
  return typeof id === "string" ? $(id) : id;
}

/** Paint the shared src / roma / zh stack. Quiz hides zh so answers do not leak.
 *  @param {{ src?: string, roma?: string, zh?: string, text?: string, romaji?: string, zhText?: string, hideSrc?: boolean, hideZh?: boolean }} opts */
export function paintLearnLine(opts) {
  const src = node(opts.src);
  const roma = node(opts.roma);
  const zh = node(opts.zh);
  const text = opts.hideSrc ? "" : String(opts.text || "");
  const romaji = opts.hideSrc ? "" : String(opts.romaji || "");
  const gloss = opts.hideZh ? "" : String(opts.zhText || "");
  if (src) {
    src.textContent = text;
    src.hidden = !text;
  }
  if (roma) {
    roma.textContent = romaji;
    roma.hidden = !romaji;
  }
  if (zh) {
    zh.textContent = gloss;
    zh.hidden = !gloss;
  }
}

export const LEARN_DIFFS = {
  easy: { id: "easy", rate: 0.8, hold: "confirm" },
  normal: { id: "normal", rate: 1, hold: 5000 },
  hard: { id: "hard", rate: 1, hold: "" }
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

export function getLearnHold() {
  return LEARN_DIFFS[getLearnDiff()].hold || "";
}

export function needsLineHold() {
  return !!getLearnHold();
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
  try {
    localStorage.setItem(DIFF_KEY, diffId);
  } catch (err) {}
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
    switchPlayerTrack(state.playerVocal);
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
    try {
      audio.currentTime = start;
    } catch (err) {}
    syncGuide(start);
    state.playerHeld = false;
    audio
      .play()
      .then(() => {
        applyPlayerVocalMix();
        requestAnimationFrame(tick);
      })
      .catch(() => resolve(false));
  });
}

export function cancelCueWindow() {
  playGen += 1;
  pausePlayerTracks();
}

let holdGen = 0;
/** @type {((ok: boolean) => void) | null} */
let holdDone = null;
let holdTimer = 0;

function finishHold(ok) {
  if (holdTimer) {
    clearInterval(holdTimer);
    holdTimer = 0;
  }
  const done = holdDone;
  holdDone = null;
  if (done) done(ok);
}

export function isLineHold() {
  return !!holdDone;
}

export function cancelLineHold() {
  holdGen += 1;
  finishHold(false);
}

export function confirmLineHold() {
  if (!holdDone) return false;
  holdGen += 1;
  finishHold(true);
  return true;
}

/** @param {{ button?: HTMLElement | null, restore?: string }} [opts] */
export function holdAfterLine(opts) {
  const hold = getLearnHold();
  if (!hold) return Promise.resolve(true);
  const button = opts && opts.button;
  const restore = (opts && opts.restore) || t("learn.next");
  const gen = ++holdGen;
  if (holdTimer) {
    clearInterval(holdTimer);
    holdTimer = 0;
  }
  return new Promise((resolve) => {
    holdDone = (ok) => {
      if (button) {
        button.textContent = restore;
        button.disabled = false;
        button.hidden = true;
      }
      resolve(!!ok);
    };
    if (button) {
      button.hidden = false;
      button.disabled = false;
    }
    if (hold === "confirm") {
      if (button) button.textContent = t("learn.next");
      return;
    }
    let left = Math.max(1, Math.ceil((Number(hold) || 5000) / 1000));
    const paint = () => {
      if (button) button.textContent = t("learn.holdWait", { n: left });
    };
    paint();
    holdTimer = window.setInterval(() => {
      if (gen !== holdGen) {
        clearInterval(holdTimer);
        holdTimer = 0;
        return;
      }
      left -= 1;
      if (left <= 0) {
        confirmLineHold();
        return;
      }
      paint();
    }, 1000);
  });
}
