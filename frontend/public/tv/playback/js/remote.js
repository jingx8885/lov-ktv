import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { state } from "../../state.js";
import { roomCode } from "../../auth/js/login.js";
import { unlockAudio } from "../../audio/js/unlock.js";
import { applyMix } from "./mix.js?v=stall1";
import { startPlayback, stopPlayback, tick } from "./tick.js?v=paint4";

function currentCode() {
  return roomCode() || (state.room && state.room.code) || "";
}

function loginOpen() {
  const gate = $("loginGate");
  return !!(gate && !gate.hidden);
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
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && karaoke && karaoke.paused) {
    startPlayback();
    return true;
  }
  return false;
}

export async function skipSong() {
  const code = currentCode();
  if (!code) return;
  const btn = $("skip");
  if (btn) btn.disabled = true;
  try {
    const { ok, data } = await fetchJson("/api/rooms/" + code + "/skip", { method: "POST" });
    if (!ok || !data.code) return;
    state.room = /** @type {Room} */ (data);
    if (!state.room.now_playing) stopPlayback();
    else state.lastItem = "";
    if (state.room.now_playing && $("title")) $("title").textContent = state.room.now_playing.title;
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

export function confirm() {
  if (loginOpen()) return;
  if (startIfNeeded()) return;
  toggleVocal();
}

function onRemoteKey(event) {
  if (event.repeat) return;
  const el = event.target;
  const tag = el && "tagName" in el ? String(el.tagName) : "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (loginOpen()) return;
  switch (event.key) {
    case "ArrowRight":
    case "MediaTrackNext":
      event.preventDefault();
      skipSong();
      break;
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
    volumeUp: () => nudgeVolume(10),
    volumeDown: () => nudgeVolume(-10),
    confirm,
    start: startIfNeeded,
    __module: true,
  };
  document.addEventListener("keydown", onRemoteKey);
}
