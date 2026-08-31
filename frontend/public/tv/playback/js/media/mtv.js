import { $ } from "../../../../shared/ui/js/dom.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { mediaRevFor, mediaUrl } from "./mix.js";
import { nativeMtvAvailable, playNativeMtv } from "../../../platform.js";

const MTV_RETRY_DELAYS_MS = [1200, 2500, 5000, 10000];

function nativePlayer() {
  return nativeMtvAvailable();
}

function killHtmlMtv(mtv) {
  if (!mtv) return;
  mtv.muted = true;
  mtv.defaultMuted = true;
  mtv.volume = 0;
  mtv.hidden = true;
  mtv.pause();
  if (mtv.getAttribute("src") || mtv.src) {
    mtv.removeAttribute("src");
    try {
      mtv.load();
    } catch (err) {}
  }
}

function glassStage(on) {
  const root = document.documentElement;
  const body = document.body;
  if (root) {
    root.style.background = on ? "transparent" : "";
    root.style.backgroundColor = on ? "transparent" : "";
  }
  if (body) {
    body.style.background = on ? "transparent" : "";
    body.style.backgroundColor = on ? "transparent" : "";
  }
}

function clearMtvRetry() {
  if (state.mtvRetryTimer) {
    clearTimeout(state.mtvRetryTimer);
    state.mtvRetryTimer = 0;
  }
}

function resetMtvRetry() {
  clearMtvRetry();
  state.mtvRetryAt = 0;
  state.mtvRetrySong = "";
  state.mtvRetryCount = 0;
}

export function silenceMtv(mtv) {
  if (!mtv) return;
  mtv.muted = true;
  mtv.defaultMuted = true;
  mtv.volume = 0;
  if (nativePlayer()) killHtmlMtv(mtv);
}

export function nativeMv() {
  if (state.room && state.room.display_mode === "lyrics") return false;
  return !!(
    (state.skeleton && state.skeleton.has_video) ||
    (state.lyrics && state.lyrics.native_video === true) ||
    document.body.classList.contains("has-native-player")
  );
}

export function syncNativeMv() {
  const on = nativeMv();
  document.body.classList.toggle("has-native-mv", on);
  const plate = $("lyricPlate");
  if (!plate) return;
  plate.classList.toggle("bare", on);
  [
    "background",
    "backgroundImage",
    "border",
    "borderRadius",
    "boxShadow",
    "backdropFilter",
    "webkitBackdropFilter",
    "padding"
  ].forEach((key) => {
    plate.style[key] = "";
  });
  if (on) {
    plate.style.background = "transparent";
    plate.style.backgroundImage = "none";
    plate.style.border = "0";
    plate.style.borderRadius = "0";
    plate.style.boxShadow = "none";
    plate.style.backdropFilter = "none";
    plate.style.webkitBackdropFilter = "none";
    plate.style.padding = "0 12px 4px";
  }
  if (!on) api.ensureStageFx();
}

export function bindMtv(songId) {
  const mtv = $("mtv");
  if (!songId) return;
  if (state.room && state.room.display_mode === "lyrics") {
    killHtmlMtv(mtv);
    document.body.classList.remove("has-mtv", "has-native-mv", "has-native-player");
    document.body.classList.remove("has-mtv-cover");
    glassStage(false);
    syncNativeMv();
    api.ensureStageFx();
    return;
  }
  const htmlSrc = mediaUrl(songId, "mtv.mp4");
  const abs = (location.origin || "") + htmlSrc;
  if (nativePlayer()) {
    killHtmlMtv(mtv);
    document.body.classList.add("has-mtv", "has-native-player");
    glassStage(true);
    syncNativeMv();
    const bindKey = songId + ":" + (mediaRevFor(songId) || "");
    if (state.boundMtvSong === bindKey) return;
    state.boundMtvSong = bindKey;
    playNativeMtv(abs);
    return;
  }
  const bindKey = songId + ":" + (mediaRevFor(songId) || "");
  if (state.mtvRetrySong && state.mtvRetrySong !== bindKey) resetMtvRetry();
  if (state.mtvRetrySong === bindKey && Date.now() < state.mtvRetryAt) return;
  if (state.boundMtvSong === bindKey && (mtv.getAttribute("src") || mtv.src)) return;
  state.boundMtvSong = bindKey;
  clearMtvRetry();
  syncNativeMv();
  const cover = mediaUrl(songId, "cover.jpg");
  silenceMtv(mtv);
  const failMtv = () => {
    if (state.boundMtvSong !== bindKey) return;
    document.body.classList.add("has-mtv-cover");
    document.body.style.backgroundImage = "url(" + cover + ")";
    mtv.hidden = true;
    mtv.pause();
    document.body.classList.remove("has-mtv");
    mtv.removeAttribute("src");
    try {
      mtv.load();
    } catch (err) {}
    state.boundMtvSong = "";
    state.mtvRetrySong = bindKey;
    const attempt = state.mtvRetryCount;
    state.mtvRetryCount = attempt + 1;
    if (attempt >= MTV_RETRY_DELAYS_MS.length) return;
    const delay = MTV_RETRY_DELAYS_MS[attempt];
    state.mtvRetryAt = Date.now() + delay;
    state.mtvRetryTimer = window.setTimeout(() => {
      state.mtvRetryTimer = 0;
      state.mtvRetryAt = 0;
      const current = state.room && state.room.now_playing;
      if (!current || current.song_id !== songId || (state.room && state.room.display_mode === "lyrics")) return;
      bindMtv(songId);
    }, delay);
  };
  mtv.onerror = failMtv;
  mtv.onloadeddata = () => {
    if (state.boundMtvSong !== bindKey) return;
    resetMtvRetry();
    silenceMtv(mtv);
    mtv.hidden = false;
    document.body.classList.add("has-mtv");
    document.body.classList.remove("has-mtv-cover");
    document.body.style.backgroundImage = "";
    syncNativeMv();
    // The karaoke audio is the master clock. Paint starts the video only after
    // audio is actually live, preventing a buffered video from running ahead.
  };
  mtv.src = htmlSrc;
  silenceMtv(mtv);
}
