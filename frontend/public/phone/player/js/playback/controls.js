import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { ICO } from "../../../ui/js/icons.js";
import { showToast } from "../../../ui/js/toast.js";
import { mediaAhead } from "./media.js";

let paintPlayerCallback = null;
export function registerPaintPlayer(fn) {
  paintPlayerCallback = fn;
}

export function setPlayIcon(playing) {
  const icon = playing ? ICO.pause : ICO.play;
  const label = playing ? t("common.pause") : t("common.play");
  ["playerPlay", "editPlay"].forEach((id) => {
    const btn = $(id);
    if (!btn) return;
    if (btn.getAttribute("aria-label") !== label) btn.innerHTML = icon;
    btn.setAttribute("aria-label", label);
    btn.classList.toggle("is-playing", !!playing);
  });
}

export function playerIsPlaying() {
  const audio = $("playerAudio");
  if (state.playerClockHold != null && !state.playerHeld) return true;
  return !!(audio && audio.src && !audio.paused);
}

export function refreshPlayIcon() {
  setPlayIcon(playerIsPlaying());
}

export function pausePlayerTracks() {
  state.playerHeld = true;
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  if (audio) audio.pause();
  if (guide) guide.pause();
  refreshPlayIcon();
}

export function unlockPlayerGesture() {
  state.playerHeld = false;
  const audio = $("playerAudio");
  if (!audio) return;
  hookPlayerAudio();
  audio.play().catch(() => {});
  const guide = $("playerGuide");
  // Start both tracks from the same media position.  Calling guide.play()
  // only after audio.play() resolves leaves a small but repeatable offset.
  if (guide && guide.getAttribute("src")) {
    try {
      guide.currentTime = audio.currentTime || 0;
    } catch (err) {}
    guide.play().catch(() => {});
  }
}

export function togglePlayer() {
  if (!state.playerSong) return showToast(t("phone.player.needSong"));
  const audio = $("playerAudio");
  hookPlayerAudio();
  if (playerIsPlaying()) {
    pausePlayerTracks();
    applyPlayerVocalMix();
    return;
  }
  state.playerHeld = false;
  setPlayIcon(true);
  kickPlayerPaint();
  // Align before starting both elements; waiting for audio.play() before
  // starting the guide makes the guide late on every resume.
  syncGuide(audio.currentTime || 0);
  const guide = $("playerGuide");
  if (guide && guide.getAttribute("src")) guide.play().catch(() => {});
  audio
    .play()
    .then(() => {
      applyPlayerVocalMix();
      refreshPlayIcon();
    })
    .catch(() => {
      pausePlayerTracks();
      showToast(t("phone.player.needTap"));
    });
}

export async function togglePlayerFullscreen() {
  const page = $("page-player");
  if (!page) return;
  try {
    if (document.fullscreenElement === page) {
      await document.exitFullscreen();
    } else if (document.fullscreenElement) {
      await document.exitFullscreen();
      await page.requestFullscreen({ navigationUI: "hide" });
    } else if (page.requestFullscreen) {
      await page.requestFullscreen({ navigationUI: "hide" });
    }
  } catch (err) {
    // Fullscreen can be denied by the browser or embedded webview.
  }
  syncPlayerFullscreen();
}

export function syncPlayerFullscreen() {
  const page = $("page-player");
  const button = $("playerFullscreen");
  if (!button) return;
  const active = !!page && document.fullscreenElement === page;
  button.classList.toggle("on", active);
  button.setAttribute("aria-label", active ? t("phone.player.exitFullscreen") : t("phone.player.fullscreen"));
}

export function playFromMs(ms) {
  if (!state.playerSong) return;
  const audio = $("playerAudio");
  const start = () => {
    hookPlayerAudio();
    try {
      audio.currentTime = Math.max(0, ms) / 1000;
    } catch (err) {}
    syncGuide(Math.max(0, ms) / 1000);
    state.playerHeld = false;
    const guide = $("playerGuide");
    if (guide && guide.getAttribute("src")) guide.play().catch(() => {});
    audio
      .play()
      .then(() => {
        applyPlayerVocalMix();
        refreshPlayIcon();
      })
      .catch(() => refreshPlayIcon());
    kickPlayerPaint();
  };
  if (audio.readyState >= 1) start();
  else audio.addEventListener("loadedmetadata", start, { once: true });
}

export function pausePlayer() {
  pausePlayerTracks();
  if (state.playerRaf) {
    cancelAnimationFrame(state.playerRaf);
    state.playerRaf = 0;
  }
}

export function kickPlayerPaint() {
  if (state.playerRaf || !paintPlayerCallback) return;
  const page = $("page-player");
  if (page && page.hidden) return;
  state.playerRaf = requestAnimationFrame(paintPlayerCallback);
}

export function applyKaraokeGain() {
  const editing = document.body.classList.contains("edit-on");
  const value = editing && !state.mixTrackOn ? 0 : 1;
  if (state.playerHook && state.playerHook.gain) state.playerHook.gain.gain.value = value;
}

export function syncGuide(forceTime) {
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  if (!guide || !guide.getAttribute("src")) return;
  const editing = document.body.classList.contains("edit-on");
  const want = !state.playerHeld && !!(audio && audio.src) && (editing ? state.voiceTrackOn : !!state.playerVocal);
  const clock = forceTime != null ? forceTime : (audio && audio.currentTime) || 0;
  if (!want) guide.playbackRate = 1;
  if (guide.readyState >= 1 && !guide.seeking) {
    const signedDrift = (guide.currentTime || 0) - clock;
    const drift = Math.abs(signedDrift);
    const slack = forceTime != null ? 0.05 : 0.015;
    const targetReady = forceTime != null || mediaAhead(guide, clock) > 0.05;
    if (drift > 0.22 && targetReady) {
      try {
        guide.currentTime = clock;
        guide.playbackRate = 1;
      } catch (err) {}
    } else if (want && audio && !audio.paused && drift > slack) {
      // Keep independent browser media clocks phase-locked without seeking
      // on every paint frame.  The bounded correction is inaudible and
      // converges ordinary decoder clock drift within a few frames.
      guide.playbackRate = Math.max(0.985, Math.min(1.015, 1 - signedDrift * 0.8));
    } else {
      guide.playbackRate = 1;
    }
  }
  guide.muted = !want;
  if (want && audio && !audio.paused) {
    if (guide.paused) guide.play().catch(() => {});
  } else {
    guide.pause();
  }
}

export function applyPlayerVocalMix() {
  applyKaraokeGain();
  syncGuide();
}

export function hookPlayerAudio() {
  const ctx = api.ensurePhoneCtx();
  state.playerHook = LovBands.hookAnalyser($("playerAudio"), state.playerHook, ctx ? { ctx } : null);
  if (state.playerHook && state.playerHook.ctx && state.playerHook.ctx.state === "suspended") {
    state.playerHook.ctx.resume().catch(() => {});
  }
  if (state.playerHook && state.playerHook.ctx) state.phoneCtx = state.playerHook.ctx;
  applyKaraokeGain();
}

export function releasePlayerClock() {
  state.playerClockHold = null;
  state.playerClockHoldAt = 0;
}

export function seekPlayerRatio(ratio) {
  const audio = $("playerAudio");
  if (!audio.duration) return;
  audio.currentTime = Math.max(0, Math.min(1, ratio)) * audio.duration;
  syncGuide(audio.currentTime);
}
