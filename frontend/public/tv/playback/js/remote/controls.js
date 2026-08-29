import { $ } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import { nativeSetupAvailable, openNativeSetup, stopNativeMtv } from "../../../platform.js";
import { roomCode } from "../../../auth/js/login.js";
import { unlockAudio } from "../../../audio/js/unlock.js";
import { applyMix } from "../media/mix.js";
import { startPlayback, stopPlayback, pauseAudio, tick, wantsResume } from "../runtime/tick.js";

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

/** @type {number} */
let settingsIndex = 0;

function settingsItems() {
  const sheet = settingsBox();
  if (!sheet) return [];
  return Array.from(sheet.querySelectorAll("[data-tv-menu]")).filter((el) => !el.hidden);
}

function focusSettingsItem(index) {
  const items = settingsItems();
  if (!items.length) return;
  const n = items.length;
  settingsIndex = ((index % n) + n) % n;
  items.forEach((el, i) => {
    const on = i === settingsIndex;
    el.classList.toggle("is-focused", on);
    if (on && typeof el.focus === "function") el.focus();
  });
}

function moveSettings(delta) {
  focusSettingsItem(settingsIndex + Number(delta || 0));
}

function activateSettings() {
  const items = settingsItems();
  const item = items[settingsIndex] || items[0];
  if (item) item.click();
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
  if (
    state.room &&
    state.room.now_playing &&
    state.room.now_playing.status === "ready" &&
    karaoke &&
    wantsResume(karaoke) &&
    !roomPaused()
  ) {
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
    stopNativeMtv();
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
    body: JSON.stringify({ vocal_mix: next })
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
    body: JSON.stringify({ paused: !!paused })
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
    body: JSON.stringify({ volume: next })
  });
  if (!data || !data.code) return;
  state.room = /** @type {Room} */ (data);
  applyMix();
}

export function paintSettings() {
  const mix = state.room && state.room.vocal_mix != null ? state.room.vocal_mix : 1;
  const on = mix > 0.5;
  const vocalValue = $("tvVocalValue");
  if (vocalValue) vocalValue.textContent = on ? t("common.vocal") : t("common.karaoke");
  const vocalItem = $("tvVocal");
  if (vocalItem) vocalItem.classList.toggle("on", on);
  const setup = $("tvSetup");
  if (setup) {
    const native = nativeSetupAvailable();
    setup.hidden = !native && !document.body.classList.contains("androidtv");
  }
}

export function openSettings() {
  const sheet = settingsBox();
  if (!sheet) return;
  paintSettings();
  sheet.hidden = false;
  const start = $("start");
  if (start) start.tabIndex = -1;
  const back = $("tvSheetBack");
  if (back) back.tabIndex = -1;
  focusSettingsItem(0);
}

export function closeSettings() {
  const sheet = settingsBox();
  if (!sheet) return;
  const active = document.activeElement;
  if (active && sheet.contains(active) && "blur" in active) {
    /** @type {HTMLElement} */ (active).blur();
  }
  settingsItems().forEach((el) => el.classList.remove("is-focused"));
  sheet.hidden = true;
  const start = $("start");
  if (start) start.tabIndex = 0;
}

export function toggleSettings() {
  if (loginOpen()) return;
  if (settingsOpen()) closeSettings();
  else openSettings();
}

export function confirm() {
  if (loginOpen()) return;
  if (settingsOpen()) {
    activateSettings();
    return;
  }
  if (startIfNeeded()) return;
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
  openNativeSetup();
}

function onRemoteKey(event) {
  if (event.repeat) return;
  const el = event.target;
  const tag = el && "tagName" in el ? String(el.tagName) : "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (loginOpen()) return;
  const inSettings = settingsOpen();
  switch (event.key) {
    case "ArrowUp":
      event.preventDefault();
      event.stopPropagation();
      if (inSettings) moveSettings(-1);
      else nudgeVolume(5);
      break;
    case "ArrowDown":
      event.preventDefault();
      event.stopPropagation();
      if (inSettings) moveSettings(1);
      else nudgeVolume(-5);
      break;
    case "Enter":
    case " ":
    case "NumpadEnter":
    case "MediaPlayPause":
      event.preventDefault();
      event.stopPropagation();
      confirm();
      break;
    case "Escape":
    case "Backspace":
      if (inSettings) {
        event.preventDefault();
        event.stopPropagation();
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
    volumeUp: () => {
      if (settingsOpen()) moveSettings(-1);
      else nudgeVolume(10);
    },
    volumeDown: () => {
      if (settingsOpen()) moveSettings(1);
      else nudgeVolume(-10);
    },
    confirm,
    start: startIfNeeded,
    settings: toggleSettings,
    back,
    __module: true
  };
  if ($("tvSkip")) $("tvSkip").onclick = () => skipSong();
  if ($("tvVocal")) $("tvVocal").onclick = () => toggleVocal();
  if ($("tvSetup")) $("tvSetup").onclick = () => openProcessSetup();
  if ($("tvSheetBack")) $("tvSheetBack").onclick = () => closeSettings();
  document.addEventListener("keydown", onRemoteKey, true);
  return () => {
    document.removeEventListener("keydown", onRemoteKey, true);
    if (window.LovKtvRemote && window.LovKtvRemote.__module) delete window.LovKtvRemote;
  };
}
