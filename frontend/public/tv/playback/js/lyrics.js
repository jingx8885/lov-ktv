import { $ } from "../../../shared/ui/js/dom.js";
import { applyLyricMode, paintLine } from "../../../shared/lyrics/js/paint.js?v=paint4";
import { state } from "../../state.js";
import { nativeMv, silenceMtv } from "./mtv.js?v=native1";
import { syncVocal } from "./mix.js?v=stall1";
import { lyricClockMs, shouldSeekNative, videoSeekMs } from "./lyric-clock.js?v=native1";

let nativeLyricsCleared = false;

function hideNativeLyrics() {
  if (nativeLyricsCleared) return;
  const native = window.LovKtvNative;
  if (!native || typeof native.clearLyrics !== "function") return;
  try { native.clearLyrics(); nativeLyricsCleared = true; } catch (err) {}
}

function syncNativeVideo(karaoke) {
  const native = window.LovKtvNative;
  if (!native || !karaoke) return;
  const live = !karaoke.paused && karaoke.readyState >= 2 && karaoke.currentTime > 0.05;
  try {
    if (karaoke.paused && karaoke.readyState >= 2 && karaoke.currentTime > 0.3) {
      if (native.pauseMtv) native.pauseMtv();
    } else if (live && native.resumeMtv) {
      native.resumeMtv();
    }
    if (!live || typeof native.positionMs !== "function" || typeof native.seekMtv !== "function") return;
    const audioMs = Math.floor((karaoke.currentTime || 0) * 1000);
    const karaokeDur = Number.isFinite(karaoke.duration) ? Math.round(karaoke.duration * 1000) : 0;
    const mtvDur = typeof native.durationMs === "function" ? Number(native.durationMs()) || 0 : 0;
    const target = videoSeekMs(audioMs, mtvDur, karaokeDur);
    const pos = Number(native.positionMs()) || 0;
    const playing = typeof native.playing === "function" ? !!native.playing() : true;
    const now = Date.now();
    if (shouldSeekNative(pos, target, state.lastMtvSeek, now, playing)) {
      state.lastMtvSeek = now;
      native.seekMtv(target);
    }
  } catch (err) {}
}

export function ensureStageFx() {
  if (state.stageFx || !window.LovStageFx) return state.stageFx;
  state.stageFx = LovStageFx.create($("stageFx"));
  LovStageFx.bindParty($("partyFx"));
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
    return Math.max(0, Math.min(1, (sum / 46) / 255));
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
    LovStageFx.celebrate(idx % 2 ? "side" : "center");
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
  const mode = applyLyricMode(
    document.body,
    (state.room && state.room.lyric_mode) || "all",
    now && now.language,
  );
  if (now && now.status === "ready") {
    const karaoke = $("karaoke");
    const mtv = $("mtv");
    const t = lyricClockMs((karaoke.currentTime || 0) * 1000, state.lyrics);
    syncVocal();
    if (window.LovKtvNative && typeof window.LovKtvNative.playMtv === "function") {
      if (mtv) {
        mtv.hidden = true;
        mtv.pause();
      }
    } else {
      silenceMtv(mtv);
      const audioLive = !karaoke.paused && karaoke.readyState >= 2 && karaoke.currentTime > 0.05;
      if (!mtv.hidden && mtv.src && Number.isFinite(mtv.duration) && mtv.readyState >= 2 && !mtv.seeking && !karaoke.seeking) {
        const target = Math.min(karaoke.currentTime || 0, Math.max(0, mtv.duration - 0.05));
        if (audioLive && Math.abs(mtv.currentTime - target) > 2 && Date.now() - state.lastMtvSeek > 1500) {
          state.lastMtvSeek = Date.now();
          try { mtv.currentTime = target; } catch (err) {}
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
      now: performance.now() / 1000,
    });
  }
  requestAnimationFrame(paint);
}
