import { $ } from "../../../shared/ui/js/dom.js";
import { state } from "../../state.js";
import { applyPlayerVocalMix, hookPlayerAudio, pausePlayerTracks, syncGuide } from "./playback.js";

let playGen = 0;

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
