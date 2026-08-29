import { $ } from "../../../shared/ui/js/dom.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { mediaUrl } from "./media.js";
import { startPhoneMic, stopPhoneMic } from "./mic.js";
import { cancelCueWindow, paintLearnLine, playCueWindow } from "./learn-play.js";

export const SING_PAD_MS = 1600;
export const SING_MIN_MS = 4200;

/** @type {LearnEchoSession} */
const session = {
  lines: [],
  index: 0,
  clips: [],
  mixUrl: "",
  running: false,
  review: null,
  previewUrl: "",
  skipped: false,
};

/** @type {HTMLAudioElement | null} */
let previewEl = null;

export function resetEcho(lines) {
  revokeMix();
  cancelPreview();
  session.lines = lines || [];
  session.index = 0;
  session.clips = [];
  session.mixUrl = "";
  session.running = false;
  session.review = null;
  session.skipped = false;
}

export function echoBusy() {
  return session.running;
}

/** @param {{ start_ms?: number, end_ms?: number }} line */
export function singWindowEnd(line) {
  const start = Number(line && line.start_ms) || 0;
  const end = Number(line && line.end_ms) || start;
  return Math.max(end + SING_PAD_MS, start + SING_MIN_MS);
}

function revokeMix() {
  if (session.mixUrl) URL.revokeObjectURL(session.mixUrl);
  session.mixUrl = "";
}

function cancelPreview() {
  if (previewEl) {
    previewEl.pause();
    previewEl.removeAttribute("src");
    previewEl = null;
  }
  if (session.previewUrl) URL.revokeObjectURL(session.previewUrl);
  session.previewUrl = "";
}

function recMime() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac"];
  return types.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) || "";
}

function paintEchoLine() {
  const line = session.lines[session.index];
  const total = session.lines.length;
  $("learnTitle").textContent = t("learn.echo");
  $("learnMeta").textContent = line ? `${session.index + 1} / ${total}` : "";
  paintLearnLine({
    src: "learnEchoSrc",
    roma: "learnEchoRoma",
    zh: "learnEchoZh",
    text: line ? line.text : "",
    romaji: line ? line.romaji : "",
    zhText: line ? line.zh : "",
  });
  const bar = $("learnEchoBar");
  if (bar) bar.style.width = total ? `${Math.round((session.index / total) * 100)}%` : "0";
}

function setPhase(name, label) {
  $("learnEchoPhase").textContent = label;
  $("learnEchoPulse").className = `learn-echo-pulse is-${name}`;
}

function showReviewDock(on) {
  const review = $("learnEchoReview");
  const skip = $("learnEchoSkip");
  if (review) review.hidden = !on;
  if (skip) skip.hidden = !!on;
}

function finishReview(action) {
  if (!session.review) return;
  const done = session.review;
  session.review = null;
  cancelPreview();
  cancelCueWindow();
  showReviewDock(false);
  done(action);
}

function waitReview() {
  return new Promise((resolve) => {
    session.review = resolve;
    showReviewDock(true);
    $("learnEchoSkip").disabled = true;
    const clip = session.clips[session.index];
    $("learnEchoPreview").disabled = !(clip && clip.blob);
  });
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

async function previewClip(clip) {
  cancelPreview();
  cancelCueWindow();
  if (!clip || !clip.blob) return;
  session.previewUrl = URL.createObjectURL(clip.blob);
  previewEl = new Audio(session.previewUrl);
  previewEl.setAttribute("playsinline", "");
  setPhase("listen", t("learn.echoPreviewing"));
  previewEl.play().catch(() => {});
  await playCueWindow(clip.start_ms, clip.rec_end_ms || clip.end_ms, { vocal: false });
  if (previewEl) {
    previewEl.pause();
    previewEl.currentTime = 0;
  }
  if (session.review) setPhase("review", t("learn.echoReview"));
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
  const fit = 1 - Math.min(1, Math.abs(Math.min(userBuf.duration, want) - want) / want);
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
    throw new Error(t("learn.mixFail"));
  }
  const last = session.clips.reduce((max, clip) => Math.max(max, clip.rec_end_ms || clip.end_ms), karaoke.duration * 1000);
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

/** @param {LearnLine} line @param {MediaStream} stream */
async function takeLine(line, stream) {
  const recEnd = singWindowEnd(line);
  while (session.running) {
    setPhase("sing", t("learn.echoYou"));
    showReviewDock(false);
    $("learnEchoSkip").hidden = false;
    $("learnEchoSkip").disabled = false;
    session.skipped = false;
    const blob = await recordWindow(stream, line.start_ms, recEnd);
    if (!session.running) return "stop";
    if (session.skipped) return "skip";
    session.clips[session.index] = {
      start_ms: line.start_ms,
      end_ms: line.end_ms,
      rec_end_ms: recEnd,
      blob,
    };
    setPhase("review", t("learn.echoReview"));
    const action = await waitReview();
    if (action === "retry") continue;
    return action;
  }
  return "stop";
}

export async function runEcho() {
  if (session.running) return null;
  if (!window.MediaRecorder) {
    showToast(t("learn.noRec"));
    return null;
  }
  session.running = true;
  showReviewDock(false);
  $("learnEchoSkip").hidden = false;
  $("learnEchoSkip").disabled = false;
  try {
    if (!state.phoneMic) await startPhoneMic();
    const stream = state.phoneMic;
    if (!stream) throw new Error(t("learn.noRec"));
    for (session.index = 0; session.index < session.lines.length; session.index += 1) {
      if (!session.running) break;
      const line = session.lines[session.index];
      paintEchoLine();
      setPhase("listen", t("learn.echoThis"));
      showReviewDock(false);
      $("learnEchoSkip").hidden = false;
      $("learnEchoSkip").disabled = false;
      session.skipped = false;
      const heard = await playCueWindow(line.start_ms, line.end_ms, { vocal: true });
      if (!session.running) break;
      if (session.skipped || !heard) {
        session.clips[session.index] = { start_ms: line.start_ms, end_ms: line.end_ms, rec_end_ms: singWindowEnd(line), blob: null };
        continue;
      }
      const action = await takeLine(line, stream);
      if (action === "stop") break;
      if (action === "skip") {
        session.clips[session.index] = { start_ms: line.start_ms, end_ms: line.end_ms, rec_end_ms: singWindowEnd(line), blob: null };
      }
    }
    if (!session.running) return null;
    setPhase("mix", t("learn.echoMix"));
    showReviewDock(false);
    $("learnEchoBar").style.width = "100%";
    const url = await mixClips();
    const score = await scoreEcho();
    score.mixUrl = url;
    return score;
  } catch (err) {
    showToast((err && err.message) || t("learn.echoFail"));
    return null;
  } finally {
    session.running = false;
    session.review = null;
    cancelPreview();
    stopPhoneMic();
    showReviewDock(false);
    $("learnEchoSkip").hidden = false;
    $("learnEchoSkip").disabled = true;
  }
}

export function skipEchoLine() {
  session.skipped = true;
  if (session.review) {
    finishReview("skip");
    return;
  }
  cancelCueWindow();
}

export function stopEcho() {
  session.running = false;
  cancelCueWindow();
  cancelPreview();
  if (session.review) finishReview("stop");
  stopPhoneMic();
}

export function paintEchoHome() {
  paintEchoLine();
  setPhase("wait", t("learn.echoListen"));
  showReviewDock(false);
  $("learnEchoSkip").hidden = false;
  $("learnEchoSkip").disabled = true;
}

/** @param {LearnQuiz} pack */
export function startEcho(pack) {
  resetEcho(pack.lines);
  paintEchoHome();
}

/** @param {any} score @param {(pct: number) => string} grade */
export function echoScoreView(score, grade) {
  return {
    title: t("learn.score.echo"),
    again: t("learn.again.echo"),
    sub: t("learn.score.sung", { grade: grade(score.pct), sung: score.sung || 0, total: score.total || 0 }),
    detail: t("learn.score.echoHint"),
    mixUrl: score.mixUrl,
  };
}

export function bindEcho() {
  $("learnEchoSkip").onclick = () => skipEchoLine();
  $("learnEchoPreview").onclick = () => {
    const clip = session.clips[session.index];
    previewClip(clip).catch(() => {});
  };
  $("learnEchoRetry").onclick = () => finishReview("retry");
  $("learnEchoNext").onclick = () => finishReview("next");
}
