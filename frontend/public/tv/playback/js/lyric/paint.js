import { $ } from "../../../../shared/ui/js/dom.js";
import { applyLyricMode, paintLine } from "../../../../shared/lyrics/js/paint.js";
import { state } from "../../../state.js";
import { nativeMv, silenceMtv } from "../media/mtv.js";
import { syncVocal } from "../media/mix.js";
import { lyricClockMs, shouldSeekNative, videoSeekMs } from "./clock.js";
import {
  clearNativeLyrics,
  nativeMtvAvailable,
  nativeMtvDurationMs,
  nativeMtvPlaying,
  nativeMtvPositionMs,
  pauseNativeMtv,
  resumeNativeMtv,
  seekNativeMtv
} from "../../../platform.js";

let nativeLyricsCleared = false;

function hideNativeLyrics() {
  if (nativeLyricsCleared) return;
  if (clearNativeLyrics()) nativeLyricsCleared = true;
}

function syncNativeVideo(karaoke) {
  if (!nativeMtvAvailable() || !karaoke) return;
  const live = !karaoke.paused && karaoke.readyState >= 2 && karaoke.currentTime > 0.05;
  try {
    if (karaoke.paused && karaoke.readyState >= 2 && karaoke.currentTime > 0.3) {
      pauseNativeMtv();
    } else if (live) {
      resumeNativeMtv();
    }
    if (!live) return;
    const audioMs = Math.floor((karaoke.currentTime || 0) * 1000);
    const karaokeDur = Number.isFinite(karaoke.duration) ? Math.round(karaoke.duration * 1000) : 0;
    const mtvDur = nativeMtvDurationMs();
    const target = videoSeekMs(audioMs, mtvDur, karaokeDur);
    const pos = nativeMtvPositionMs();
    const playing = nativeMtvPlaying();
    const now = Date.now();
    if (shouldSeekNative(pos, target, state.lastMtvSeek, now, playing)) {
      state.lastMtvSeek = now;
      seekNativeMtv(target);
    }
  } catch (err) {}
}

export function ensureStageFx() {
  if (state.stageFx || !window.LovStageFxRuntime) return state.stageFx;
  state.stageFx = LovStageFxRuntime.create($("stageFx"));
  LovStageFxParty.bind($("partyFx"));
  return state.stageFx;
}

export function liveBeat() {
  if (!state.audioHook) return 0;
  const freq = state.audioHook.freq;
  const wave = state.audioHook.time;
  let peak = 0;
  let sum = 0;
  if (wave && wave.length) {
    const step = Math.max(1, Math.floor(wave.length / 160));
    for (let i = 0; i < wave.length; i += step) {
      const v = (wave[i] - 128) / 128;
      sum += v * v;
      peak = Math.max(peak, Math.abs(v));
    }
    const rms = Math.sqrt(sum / Math.max(1, Math.floor(wave.length / step)));
    return Math.max(0, Math.min(1, rms * 0.7 + peak * 0.5));
  }
  if (freq && freq.length) {
    for (let i = 2; i < Math.min(48, freq.length); i += 1) sum += freq[i];
    return Math.max(0, Math.min(1, sum / 46 / 255));
  }
  return 0;
}

export function fireCueFx(cue, idx) {
  if (nativeMv() || !cue || idx < 0 || idx === state.lastFxCue) return;
  state.lastFxCue = idx;
  const fx = ensureStageFx();
  if (fx) fx.spawn();
  const text = String(cue.text || "").trim();
  const now = Date.now();
  if (text && state.hookLines.has(text) && now - state.lastCelebrateAt > 8000) {
    state.lastCelebrateAt = now;
    LovStageFxParty.celebrate(idx % 2 ? "side" : "center");
  }
}

export function lyricsFingerprint(data) {
  const cues = (data && data.cues) || [];
  if (!cues.length) return "0";
  const first = cues[0];
  const last = cues[cues.length - 1];
  return [cues.length, first.start_ms, first.text, last.start_ms, last.text].join("|");
}

export function paint() {
  const now = state.room && state.room.now_playing;
  const mode = applyLyricMode(document.body, (state.room && state.room.lyric_mode) || "all", now && now.language);
  if (now && now.status === "ready") {
    const karaoke = $("karaoke");
    const mtv = $("mtv");
    const t = lyricClockMs((karaoke.currentTime || 0) * 1000, state.lyrics);
    syncVocal();
    if (nativeMtvAvailable()) {
      if (mtv) {
        mtv.hidden = true;
        mtv.pause();
      }
    } else {
      silenceMtv(mtv);
      const audioLive = !karaoke.paused && karaoke.readyState >= 2 && karaoke.currentTime > 0.05;
      if (
        !mtv.hidden &&
        mtv.src &&
        Number.isFinite(mtv.duration) &&
        mtv.readyState >= 2 &&
        !mtv.seeking &&
        !karaoke.seeking
      ) {
        const target = Math.min(karaoke.currentTime || 0, Math.max(0, mtv.duration - 0.05));
        if (audioLive && Math.abs(mtv.currentTime - target) > 2 && Date.now() - state.lastMtvSeek > 1500) {
          state.lastMtvSeek = Date.now();
          try {
            mtv.currentTime = target;
          } catch (err) {}
        }
        if (karaoke.paused) mtv.pause();
        else if (audioLive && mtv.paused && !mtv.ended) mtv.play().catch(() => {});
      }
    }
    const cues = state.lyrics.cues || [];
    const idx = cues.findIndex((c) => t >= c.start_ms && t < c.end_ms);
    const cue = idx >= 0 ? cues[idx] : null;
    const upcomingIdx = cues.findIndex((c) => t < c.start_ms);
    if (cue) {
      fireCueFx(cue, idx);
      paintLine($("prev"), idx > 0 ? cues[idx - 1] : null, 1e12, "prev", state.lyricPaint, "", mode);
      paintLine($("cur"), cue, t, "cur", state.lyricPaint, "", mode);
      paintLine($("next"), cues[idx + 1] || null, -1, "next", state.lyricPaint, "", mode);
      hideNativeLyrics();
    } else if (upcomingIdx >= 0) {
      const held = upcomingIdx > 0 ? cues[upcomingIdx - 1] : null;
      paintLine($("prev"), upcomingIdx > 1 ? cues[upcomingIdx - 2] : null, 1e12, "prev", state.lyricPaint, "", mode);
      paintLine($("cur"), held, 1e12, "cur", state.lyricPaint, "", mode);
      paintLine($("next"), cues[upcomingIdx], -1, "next", state.lyricPaint, "", mode);
      hideNativeLyrics();
    } else {
      paintLine($("prev"), cues.length ? cues[cues.length - 1] : null, 1e12, "prev", state.lyricPaint, "", mode);
      paintLine($("cur"), null, t, "cur", state.lyricPaint, "", mode);
      paintLine($("next"), null, -1, "next", state.lyricPaint, "", mode);
      hideNativeLyrics();
    }
    syncNativeVideo(karaoke);
  }
  if (state.audioHook && !nativeMv()) LovBands.pull(state.audioHook);
  if (state.stageFx && !nativeMv()) {
    state.stageFx.draw({
      beat: now && now.status === "ready" ? liveBeat() : 0,
      now: performance.now() / 1000
    });
  }
  requestAnimationFrame(paint);
}
