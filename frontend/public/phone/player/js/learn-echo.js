import { $ } from "../../../shared/ui/js/dom.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { mediaUrl } from "./playback.js";
import { acquirePhoneMic, startPhoneMic, stopPhoneMic } from "./mic.js";
import { cancelCueWindow, playCueWindow } from "./learn-play.js";

/** @type {LearnEchoSession} */
const session = {
  lines: [],
  index: 0,
  clips: [],
  mixUrl: "",
  running: false,
};

export function resetEcho(lines) {
  revokeMix();
  session.lines = lines || [];
  session.index = 0;
  session.clips = [];
  session.mixUrl = "";
  session.running = false;
}

export function echoBusy() {
  return session.running;
}

function revokeMix() {
  if (session.mixUrl) URL.revokeObjectURL(session.mixUrl);
  session.mixUrl = "";
}

function recMime() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac"];
  return types.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) || "";
}

function paintEchoLine() {
  const line = session.lines[session.index];
  const total = session.lines.length;
  $("learnTitle").textContent = "跟唱合成";
  $("learnMeta").textContent = line ? `${session.index + 1} / ${total}` : "";
  $("learnEchoSrc").textContent = line ? line.text : "";
  $("learnEchoRoma").textContent = (line && line.romaji) || "";
  $("learnEchoRoma").hidden = !(line && line.romaji);
  $("learnEchoZh").textContent = (line && line.zh) || "";
  $("learnEchoZh").hidden = !(line && line.zh);
  const bar = $("learnEchoBar");
  if (bar) bar.style.width = total ? `${Math.round((session.index / total) * 100)}%` : "0";
}

function setPhase(name, label) {
  $("learnEchoPhase").textContent = label;
  $("learnEchoPulse").className = `learn-echo-pulse is-${name}`;
}

/** @param {MediaStream} stream @param {number} startMs @param {number} endMs */
function recordWindow(stream, startMs, endMs) {
  const mime = recMime();
  const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
  const chunks = [];
  rec.ondataavailable = (event) => {
    if (event.data && event.data.size) chunks.push(event.data);
  };
  const done = new Promise((resolve) => {
    rec.onstop = () => resolve(new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" }));
    rec.onerror = () => resolve(null);
  });
  rec.start();
  return playCueWindow(startMs, endMs, { vocal: false }).then((ok) => {
    if (rec.state !== "inactive") rec.stop();
    return done.then((blob) => (ok && blob && blob.size ? blob : null));
  });
}

async function decodeBuffer(ctx, data) {
  try {
    return await ctx.decodeAudioData(data.slice(0));
  } catch (err) {
    return new Promise((resolve, reject) => {
      ctx.decodeAudioData(data.slice(0), resolve, reject);
    });
  }
}

function frameRms(channel, size) {
  const out = [];
  for (let i = 0; i < channel.length; i += size) {
    let sum = 0;
    const end = Math.min(channel.length, i + size);
    for (let j = i; j < end; j += 1) sum += channel[j] * channel[j];
    out.push(Math.sqrt(sum / Math.max(1, end - i)));
  }
  return out;
}

function pearson(a, b) {
  const n = Math.min(a.length, b.length);
  if (n < 3) return 0;
  let sa = 0;
  let sb = 0;
  for (let i = 0; i < n; i += 1) {
    sa += a[i];
    sb += b[i];
  }
  const ma = sa / n;
  const mb = sb / n;
  let num = 0;
  let da = 0;
  let db = 0;
  for (let i = 0; i < n; i += 1) {
    const xa = a[i] - ma;
    const xb = b[i] - mb;
    num += xa * xb;
    da += xa * xa;
    db += xb * xb;
  }
  if (!da || !db) return 0;
  return num / Math.sqrt(da * db);
}

function scoreClip(userBuf, guideBuf, startMs, endMs) {
  const user = userBuf.getChannelData(0);
  const frames = frameRms(user, Math.round(userBuf.sampleRate * 0.05));
  const peak = Math.max(...frames, 0.0001);
  const cover = frames.filter((value) => value > peak * 0.12).length / Math.max(1, frames.length);
  const want = Math.max(0.2, (endMs - startMs) / 1000);
  const fit = 1 - Math.min(1, Math.abs(userBuf.duration - want) / want);
  let vibe = 0.55;
  if (guideBuf) {
    const rate = guideBuf.sampleRate;
    const from = Math.floor((startMs / 1000) * rate);
    const to = Math.min(guideBuf.length, Math.floor((endMs / 1000) * rate));
    if (to > from + 64) {
      const guide = guideBuf.getChannelData(0).subarray(from, to);
      const gFrames = frameRms(guide, Math.round(rate * 0.05));
      vibe = Math.max(0, pearson(frames, gFrames));
    }
  }
  return Math.round(Math.max(0, Math.min(100, cover * 48 + Math.max(0, vibe) * 36 + fit * 16)));
}

function writeWav(buffer) {
  const channels = buffer.numberOfChannels;
  const rate = buffer.sampleRate;
  const samples = buffer.length;
  const bytes = samples * channels * 2;
  const view = new DataView(new ArrayBuffer(44 + bytes));
  const ascii = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + bytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * channels * 2, true);
  view.setUint16(32, channels * 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, bytes, true);
  let offset = 44;
  for (let i = 0; i < samples; i += 1) {
    for (let ch = 0; ch < channels; ch += 1) {
      const sample = Math.max(-1, Math.min(1, buffer.getChannelData(ch)[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }
  }
  return new Blob([view.buffer], { type: "audio/wav" });
}

async function loadSongBuffer(ctx) {
  const song = state.playerSong;
  if (!song) return null;
  for (const name of ["karaoke.m4a", "original.mp3"]) {
    try {
      const res = await fetch(mediaUrl(song.id, name));
      if (!res.ok) continue;
      return await decodeBuffer(ctx, await res.arrayBuffer());
    } catch (err) {}
  }
  return null;
}

async function loadGuideBuffer(ctx) {
  const song = state.playerSong;
  if (!song) return null;
  try {
    const res = await fetch(mediaUrl(song.id, "guide.m4a"));
    if (!res.ok) return null;
    return await decodeBuffer(ctx, await res.arrayBuffer());
  } catch (err) {
    return null;
  }
}

async function mixClips() {
  revokeMix();
  const live = new (window.AudioContext || window.webkitAudioContext)();
  const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const karaoke = await loadSongBuffer(live);
  if (!karaoke || !Offline) {
    live.close().catch(() => {});
    throw new Error("合不成伴奏");
  }
  const last = session.clips.reduce((max, clip) => Math.max(max, clip.end_ms), karaoke.duration * 1000);
  const length = Math.ceil(Math.max(karaoke.duration, last / 1000 + 0.2) * karaoke.sampleRate);
  const offline = new Offline(karaoke.numberOfChannels, length, karaoke.sampleRate);
  const bed = offline.createBufferSource();
  bed.buffer = karaoke;
  bed.connect(offline.destination);
  bed.start(0);
  for (const clip of session.clips) {
    if (!clip.blob) continue;
    try {
      const buf = await decodeBuffer(offline, await clip.blob.arrayBuffer());
      const src = offline.createBufferSource();
      const gain = offline.createGain();
      src.buffer = buf;
      gain.gain.value = 1.15;
      src.connect(gain);
      gain.connect(offline.destination);
      src.start(Math.max(0, clip.start_ms / 1000));
    } catch (err) {}
  }
  const rendered = await offline.startRendering();
  const blob = writeWav(rendered);
  session.mixUrl = URL.createObjectURL(blob);
  live.close().catch(() => {});
  return session.mixUrl;
}

export async function scoreEcho() {
  const live = new (window.AudioContext || window.webkitAudioContext)();
  const guide = await loadGuideBuffer(live);
  const marks = [];
  for (const clip of session.clips) {
    if (!clip.blob) {
      marks.push(0);
      continue;
    }
    try {
      const buf = await decodeBuffer(live, await clip.blob.arrayBuffer());
      marks.push(scoreClip(buf, guide, clip.start_ms, clip.end_ms));
    } catch (err) {
      marks.push(40);
    }
  }
  live.close().catch(() => {});
  const sung = marks.filter((_, i) => session.clips[i] && session.clips[i].blob);
  const pct = sung.length ? Math.round(sung.reduce((a, b) => a + b, 0) / sung.length) : 0;
  return { pct, sung: sung.length, total: session.lines.length, mixUrl: session.mixUrl };
}

export async function runEcho() {
  if (session.running) return null;
  if (!window.MediaRecorder) {
    showToast("这台手机不能录音");
    return null;
  }
  session.running = true;
  $("learnEchoGo").disabled = true;
  $("learnEchoSkip").disabled = false;
  try {
    await startPhoneMic();
    const stream = state.phoneMic || await acquirePhoneMic();
    if (!stream) throw new Error("开麦失败");
    for (session.index = 0; session.index < session.lines.length; session.index += 1) {
      if (!session.running) break;
      const line = session.lines[session.index];
      paintEchoLine();
      setPhase("listen", "听这句");
      await playCueWindow(line.start_ms, line.end_ms, { vocal: true });
      if (!session.running) break;
      setPhase("sing", "轮到你了");
      const blob = await recordWindow(stream, line.start_ms, line.end_ms);
      session.clips[session.index] = { start_ms: line.start_ms, end_ms: line.end_ms, blob };
    }
    if (!session.running) return null;
    setPhase("mix", "正在合成…");
    $("learnEchoBar").style.width = "100%";
    const url = await mixClips();
    const score = await scoreEcho();
    score.mixUrl = url;
    return score;
  } catch (err) {
    showToast((err && err.message) || "跟唱失败");
    return null;
  } finally {
    session.running = false;
    stopPhoneMic();
    $("learnEchoGo").disabled = false;
  }
}

export function skipEchoLine() {
  cancelCueWindow();
}

export function stopEcho() {
  session.running = false;
  cancelCueWindow();
  stopPhoneMic();
}

export function paintEchoHome() {
  paintEchoLine();
  setPhase("wait", "先听原唱，再对着伴奏唱回去");
  $("learnEchoGo").disabled = false;
  $("learnEchoGo").textContent = "开始跟唱";
}
