import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { state } from "../../state.js";
import { roomCode } from "../../auth/js/login.js";
import { unlockAudio } from "../../audio/js/unlock.js";
import { applyMix } from "./mix.js";
import { startPlayback, stopPlayback, pauseAudio, tick, wantsResume } from "./tick.js";

function currentCode() {
  return roomCode() || (state.room && state.room.code) || "";
}

function loginOpen() {
  const gate = $("loginGate");
  return !!(gate && !gate.hidden);
}

function settingsBox() {
  return $("tvSheet");
}

export function settingsOpen() {
  const sheet = settingsBox();
  return !!(sheet && !sheet.hidden);
}

function roomPaused() {
  return !!(state.room && state.room.paused);
}

export function applyPaused() {
  paintSettings();
  if (roomPaused()) {
    pauseAudio();
    return;
  }
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready") {
    startPlayback();
  }
}

function startIfNeeded() {
  unlockAudio();
  const gate = $("gate");
  const start = $("start");
  if (gate && !gate.hidden && start) {
    start.click();
    return true;
  }
  const karaoke = $("karaoke");
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && karaoke && wantsResume(karaoke) && !roomPaused()) {
    startPlayback();
    return true;
  }
  return false;
}

export async function skipSong() {
  const code = currentCode();
  if (!code) return;
  const btn = $("skip") || $("tvSkip");
  if (btn) btn.disabled = true;
  try {
    const { ok, data } = await fetchJson("/api/rooms/" + code + "/skip", { method: "POST" });
    if (!ok || !data.code) return;
    state.room = /** @type {Room} */ (data);
    try { if (window.LovKtvNative && window.LovKtvNative.stopMtv) window.LovKtvNative.stopMtv(); } catch (err) {}
    state.boundMtvSong = "";
    if (!state.room.now_playing) stopPlayback();
    else state.lastItem = "";
    if (state.room.now_playing && $("title")) $("title").textContent = state.room.now_playing.title;
    closeSettings();
    await tick();
  } finally {
    if (btn) btn.disabled = false;
  }
}

export async function toggleVocal() {
  const code = currentCode();
  if (!code || !state.room) return;
  const next = (state.room.vocal_mix || 0) > 0.5 ? 0 : 1;
  const { data } = await fetchJson("/api/rooms/" + code + "/mix", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vocal_mix: next }),
  });
  if (!data || !data.code) return;
  state.room = /** @type {Room} */ (data);
  applyMix();
  paintSettings();
}

export async function setPaused(paused) {
  const code = currentCode();
  if (!code) return;
  const { data } = await fetchJson("/api/rooms/" + code + "/mix", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paused: !!paused }),
  });
  if (!data || !data.code) return;
  state.room = /** @type {Room} */ (data);
  applyPaused();
}

export async function togglePaused() {
  if (!state.room || !state.room.now_playing) {
    startIfNeeded();
    return;
  }
  await setPaused(!roomPaused());
}

export async function nudgeVolume(delta) {
  const code = currentCode();
  if (!code) return;
  const cur = state.room && state.room.volume != null ? Number(state.room.volume) : 80;
  const next = Math.max(0, Math.min(100, cur + Number(delta || 0)));
  if (state.room) state.room.volume = next;
  applyMix();
  const { data } = await fetchJson("/api/rooms/" + code + "/mix", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ volume: next }),
  });
  if (!data || !data.code) return;
  state.room = /** @type {Room} */ (data);
  applyMix();
}

export function paintSettings() {
  const vocal = $("tvVocal");
  if (vocal) {
    const on = (state.room && state.room.vocal_mix || 0) > 0.5;
    vocal.textContent = on ? t("common.vocal") : t("common.karaoke");
    vocal.classList.toggle("on", on);
  }
}

export function openSettings() {
  const sheet = settingsBox();
  if (!sheet) return;
  paintSettings();
  sheet.hidden = false;
  const skip = $("tvSkip");
  if (skip) skip.focus();
}

export function closeSettings() {
  const sheet = settingsBox();
  if (sheet) sheet.hidden = true;
}

export function toggleSettings() {
  if (loginOpen()) return;
  if (settingsOpen()) closeSettings();
  else openSettings();
}

export function confirm() {
  if (loginOpen()) return;
  if (settingsOpen()) return;
  if (startIfNeeded() && roomPaused()) return;
  togglePaused();
}

export function back() {
  if (settingsOpen()) {
    closeSettings();
    return true;
  }
  return false;
}

function openProcessSetup() {
  try {
    if (window.LovKtvNative && typeof window.LovKtvNative.openSetup === "function") {
      window.LovKtvNative.openSetup();
    }
  } catch (err) {}
}

function onRemoteKey(event) {
  if (event.repeat) return;
  const el = event.target;
  const tag = el && "tagName" in el ? String(el.tagName) : "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (loginOpen()) return;
  switch (event.key) {
    case "ArrowUp":
      event.preventDefault();
      nudgeVolume(5);
      break;
    case "ArrowDown":
      event.preventDefault();
      nudgeVolume(-5);
      break;
    case "Enter":
    case " ":
    case "MediaPlayPause":
      event.preventDefault();
      confirm();
      break;
    case "Escape":
    case "Backspace":
      if (settingsOpen()) {
        event.preventDefault();
        closeSettings();
      }
      break;
    default:
      break;
  }
}

export function bindRemote() {
  if (new URLSearchParams(location.search).has("androidtv")) {
    document.body.classList.add("androidtv");
    const hint = $("remoteHint");
    if (hint) hint.hidden = false;
  }
  window.LovKtvRemote = {
    skip: skipSong,
    toggleVocal,
    togglePaused,
    volumeUp: () => nudgeVolume(10),
    volumeDown: () => nudgeVolume(-10),
    confirm,
    start: startIfNeeded,
    settings: toggleSettings,
    back,
    __module: true,
  };
  if ($("tvSkip")) $("tvSkip").onclick = () => skipSong();
  if ($("tvVocal")) $("tvVocal").onclick = () => toggleVocal();
  if ($("tvSetup")) $("tvSetup").onclick = () => openProcessSetup();
  if ($("tvSheetBack")) $("tvSheetBack").onclick = () => closeSettings();
  document.addEventListener("keydown", onRemoteKey);
}
