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
  if (guide && guide.getAttribute("src") && state.playerVocal) guide.play().catch(() => {});
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
  const clock = forceTime != null ? forceTime : audio.currentTime || 0;
  if (guide.readyState >= 1 && !guide.seeking) {
    const drift = Math.abs((guide.currentTime || 0) - clock);
    const slack = forceTime != null ? 0.05 : 0.12;
    const targetReady = forceTime != null || mediaAhead(guide, clock) > 0.05;
    if (drift > slack && targetReady) {
      try {
        guide.currentTime = clock;
      } catch (err) {}
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
