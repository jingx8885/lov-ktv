import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { liveCtxs, resumeCtxs } from "./unlock.js";
import { wantsResume } from "../../playback/js/tick.js";

export function makeQuietLoop() {
  const sr = 44100;
  const n = Math.floor(sr * 0.5);
  const dataSize = n * 2;
  const buf = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buf);
  const write = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sr, true);
  view.setUint32(28, sr * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, dataSize, true);
  for (let i = 0; i < n; i += 1) {
    view.setInt16(44 + i * 2, Math.sin((2 * Math.PI * 17000 * i) / sr) * 900, true);
  }
  return URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
}

export function startKeepAliveTone() {
  const ctx = liveCtxs()[0];
  if (!ctx || state.keepAliveTone) return;
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 20;
    gain.gain.value = 0.00003;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    state.keepAliveTone = { osc, gain };
  } catch (_) {}
}

export function pumpKeepAlive() {
  const el = $("keepAlive");
  if (el) {
    if (!state.keepAliveSrc) state.keepAliveSrc = makeQuietLoop();
    if (!el.getAttribute("src")) {
      el.src = state.keepAliveSrc;
      el.loop = true;
      el.muted = false;
      el.volume = 0.04;
    }
    if (el.paused) el.play().catch(() => {});
  }
  resumeCtxs();
  startKeepAliveTone();
}

export function startKeepAlive() {
  pumpKeepAlive();
  if (state.keepAliveTimer) return;
  state.keepAliveTimer = setInterval(() => {
    if (!state.audioUnlocked) return;
    pumpKeepAlive();
    const now = state.room && state.room.now_playing;
    const karaoke = $("karaoke");
    if (now && now.status === "ready" && wantsResume(karaoke) && api.pageVisible() && state.isLeader) {
      api.startPlayback();
    }
  }, 1500);
}

export function schedulePlayRetries() {
  if (state.playRetryTimer) return;
  const delays = [250, 600, 1200, 2500, 5000];
  let n = 0;
  const step = () => {
    const now = state.room && state.room.now_playing;
    const karaoke = $("karaoke");
    if (!now || now.status !== "ready") {
      state.playRetryTimer = 0;
      return;
    }
    if (karaoke && !karaoke.paused && karaoke.getAttribute("src")) {
      $("gate").hidden = true;
      state.playRetryTimer = 0;
      return;
    }
    if (!wantsResume(karaoke)) {
      state.playRetryTimer = 0;
      return;
    }
    if (api.pageVisible() && state.isLeader) api.startPlayback();
    if (n < delays.length) {
      state.playRetryTimer = setTimeout(step, delays[n]);
      n += 1;
    } else {
      state.playRetryTimer = 0;
      if (karaoke && karaoke.paused) $("gate").hidden = false;
    }
  };
  state.playRetryTimer = setTimeout(step, delays[n]);
  n += 1;
}
