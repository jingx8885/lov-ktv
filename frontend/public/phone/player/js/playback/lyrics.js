import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { syncLine, updateLineFills, cueIndexAt as cueIndexAtCues } from "../../../../shared/lyrics/js/paint.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { refreshPlayIcon, registerPaintPlayer, syncGuide } from "./controls.js";
import { releasePlayerMtv } from "./media.js";

let lastPaintAt = 0;
let lastNowText = "";
let lastLeftText = "";
// Keep the expensive source fingerprint out of the playback hot path:
// playerLyrics.cues is replaced when a song/lyrics document changes, but is
// otherwise stable while the song is playing.
let scrollCuesRef = null;
let scrollCuesKey = "";

export function cueIndexAt(time) {
  return cueIndexAtCues(state.playerLyrics.cues || [], lyricClockMs(time));
}

export function fmtClock(ms) {
  const n = Math.max(0, Math.floor((ms || 0) / 1000));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}

function playerIdleLyric() {
  return state.playerSong ? "" : t("phone.player.idle");
}

function lyricClockMs(audioMs) {
  const raw = state.playerLyrics && (state.playerLyrics.offset_ms ?? state.playerLyrics.lyric_offset_ms);
  const offset = Number(raw);
  return Math.max(0, Math.round(Number(audioMs) || 0) + (Number.isFinite(offset) ? offset : 0));
}

function videoClockSec(audio, video) {
  const audioDuration = Number(audio && audio.duration) || 0;
  const videoDuration = Number(video && video.duration) || 0;
  const extra = videoDuration - audioDuration;
  const lead = extra >= 1.5 && extra <= 30 ? extra : 0;
  return Math.max(0, (Number(audio && audio.currentTime) || 0) + lead);
}

function paintPlayerScroll(cues, time, mode, index) {
  const list = $("playerLyricScroll");
  if (!list) return;
  if (cues !== scrollCuesRef) {
    scrollCuesRef = cues;
    scrollCuesKey = cues.map((cue) => "" + cue.start_ms + ":" + cue.end_ms + ":" + (cue.text || "")).join("|");
  }
  const lyricTime = lyricClockMs(time);
  // Keep only the previous, current, and next two cues in the DOM. Rendering
  // the complete lyric document here made long songs expensive in WebView.
  const start = index >= 0 ? Math.max(0, index - 1) : 0;
  const end = index >= 0 ? Math.min(cues.length, index + 3) : 0;
  const windowKey = scrollCuesKey + ":" + start + ":" + end + ":" + mode;
  if (list.dataset.windowKey !== windowKey) {
    list.textContent = "";
    list.dataset.windowKey = windowKey;
    state.lyricPaint.scroll = { prev: "", cur: "", next: "" };
    const fragment = document.createDocumentFragment();
    for (let cueIndex = start; cueIndex < end; cueIndex += 1) {
      const row = document.createElement("div");
      row.className = "player-lyric-scroll-line line";
      row.dataset.cueIndex = String(cueIndex);
      fragment.appendChild(row);
    }
    list.appendChild(fragment);
    list.scrollTop = 0;
  }
  // syncLine writes markup and measures in one phase per row; updateLineFills
  // afterwards writes progress widths, so no layout read follows a style write.
  const pending = [];
  const rows = list.children;
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];
    const cueIndex = Number(row.dataset.cueIndex);
    const cue = cues[cueIndex];
    const rowTime = cueIndex === index && lyricTime < cue.end_ms ? lyricTime : cueIndex < index ? 1e12 : -1;
    const slot = "scroll:" + cueIndex;
    if (syncLine(row, cue, rowTime, slot, state.lyricPaint.scroll, "", mode)) {
      pending.push([row, cue, rowTime, slot]);
    }
    row.classList.toggle("is-current", cueIndex === index);
  }
  pending.forEach(([row, cue, rowTime, slot]) => updateLineFills(row, cue, rowTime, slot, state.lyricPaint.scroll));
}

export function paintPlayer() {
  const page = $("page-player");
  if (page && page.hidden) {
    state.playerRaf = 0;
    lastPaintAt = 0;
    return;
  }
  const frameNow = performance.now();
  if (frameNow - lastPaintAt < 33) {
    state.playerRaf = requestAnimationFrame(paintPlayer);
    return;
  }
  lastPaintAt = frameNow;
  const audio = $("playerAudio");
  const hold = state.playerClockHold;
  const time = Math.floor((hold != null ? hold : audio.currentTime || 0) * 1000);
  const cues = state.playerLyrics.cues || [];
  const mode = document.body.dataset.lyricMode || state.lyricMode || "all";
  const lyricsOnly = document.body.classList.contains("display-lyrics");
  const scroll = $("playerLyricScroll");
  const prevEl = $("playerPrev");
  const curEl = $("playerCur");
  const nextEl = $("playerNext");
  if (scroll && scroll.hidden === lyricsOnly) scroll.hidden = !lyricsOnly;
  [prevEl, curEl, nextEl].forEach((el) => {
    if (el && el.hidden !== lyricsOnly) el.hidden = lyricsOnly;
  });
  const lyricTime = lyricClockMs(time);
  const index = cueIndexAtCues(cues, lyricTime);
  const idx = index >= 0 && lyricTime >= cues[index].start_ms && lyricTime < cues[index].end_ms ? index : -1;
  const upcomingIdx = idx < 0 && index >= 0 ? index : -1;
  // Phase 1 writes markup and measures; fills land in phase 2 so no frame
  // reads layout after a style write on the same row.
  const pending = [];
  if (lyricsOnly) paintPlayerScroll(cues, time, mode, index);
  if (!lyricsOnly && idx >= 0) {
    if (syncLine(prevEl, idx > 0 ? cues[idx - 1] : null, 1e12, "prev", state.lyricPaint, "", mode)) {
      pending.push([prevEl, cues[idx - 1], 1e12, "prev"]);
    }
    if (syncLine(curEl, cues[idx], lyricTime, "cur", state.lyricPaint, "", mode)) {
      pending.push([curEl, cues[idx], lyricTime, "cur"]);
    }
    if (syncLine(nextEl, cues[idx + 1] || null, -1, "next", state.lyricPaint, "", mode)) {
      pending.push([nextEl, cues[idx + 1], -1, "next"]);
    }
  } else if (!lyricsOnly && upcomingIdx >= 0) {
    const held = upcomingIdx > 0 ? cues[upcomingIdx - 1] : null;
    if (syncLine(prevEl, upcomingIdx > 1 ? cues[upcomingIdx - 2] : null, 1e12, "prev", state.lyricPaint, "", mode)) {
      pending.push([prevEl, cues[upcomingIdx - 2], 1e12, "prev"]);
    }
    if (syncLine(curEl, held, held ? 1e12 : 0, "cur", state.lyricPaint, "", mode)) {
      pending.push([curEl, held, 1e12, "cur"]);
    }
    if (syncLine(nextEl, cues[upcomingIdx], -1, "next", state.lyricPaint, "", mode)) {
      pending.push([nextEl, cues[upcomingIdx], -1, "next"]);
    }
  } else if (!lyricsOnly) {
    if (syncLine(prevEl, cues.length ? cues[cues.length - 1] : null, 1e12, "prev", state.lyricPaint, "", mode)) {
      pending.push([prevEl, cues[cues.length - 1], 1e12, "prev"]);
    }
    if (syncLine(curEl, null, 0, "cur", state.lyricPaint, playerIdleLyric(), mode)) {
      pending.push([curEl, null, 0, "cur"]);
    }
    if (syncLine(nextEl, null, 0, "next", state.lyricPaint, "", mode)) {
      pending.push([nextEl, null, 0, "next"]);
    }
  }
  pending.forEach(([el, cue, t, slot]) => updateLineFills(el, cue, t, slot, state.lyricPaint));
  const dragging = !!(state.alignTl && state.alignTl.isDragging());
  if (index !== state.selectedCue && !dragging) state.selectedCue = index;
  if (document.body.classList.contains("edit-on")) api.updateAlignNow(time);
  const durSec = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : state.playerHoldDur;
  const dur = (durSec || 0) * 1000;
  const nowText = fmtClock(time);
  const leftText = dur ? "−" + fmtClock(Math.max(0, dur - time)) : "−0:00";
  if (nowText !== lastNowText) {
    lastNowText = nowText;
    ["playerNow", "playerNowDock"].forEach((id) => {
      const el = $(id);
      if (el) el.textContent = nowText;
    });
  }
  if (leftText !== lastLeftText) {
    lastLeftText = leftText;
    ["playerLeft", "playerLeftDock"].forEach((id) => {
      const el = $(id);
      if (el) el.textContent = leftText;
    });
  }
  ["playerSeek", "playerSeekDock"].forEach((id) => {
    const seek = $(id);
    if (!seek) return;
    const active = seek.matches(":active");
    const ratio = durSec ? Math.max(0, Math.min(1, time / 1000 / durSec)) : 0;
    if (!active && durSec && seek.value !== String(Math.round(ratio * 1000))) seek.value = String(Math.round(ratio * 1000));
    const shown = active ? Number(seek.value) / 1000 : ratio;
    // Sub-percent changes repaint the same gradient; halving the precision
    // skips a style write on most frames.
    const pct = active ? shown * 100 : Math.round(shown * 200) / 2;
    if (seek.dataset.p !== String(pct)) {
      seek.dataset.p = String(pct);
      seek.style.setProperty("--seek-p", pct + "%");
    }
  });
  const mtv = $("playerMtv");
  const art = $("playerArt");
  if (mtv) {
    const showMtv = document.body.classList.contains("display-mv") && !!mtv.src;
    const hasMtv = !!mtv.src;
    if (mtv.hidden === showMtv) mtv.hidden = !showMtv;
    if (art && art.classList.contains("has-mtv") !== showMtv) art.classList.toggle("has-mtv", showMtv);
    // The fullscreen affordance follows the same rule as the video surface so
    // it cannot linger after an MV fails to load or a song without MV starts.
    const fullscreen = $("playerFullscreen");
    if (fullscreen && !document.body.classList.contains("player-fullscreen") && fullscreen.hidden === showMtv) fullscreen.hidden = !showMtv;
    // Keep a loaded MV warm while lyrics are shown so switching back is
    // immediate instead of waiting for another decode/buffer cycle.
    if (hasMtv && Number.isFinite(mtv.duration) && mtv.readyState >= 2) {
      const target = videoClockSec(audio, mtv);
      const drift = Math.abs((mtv.currentTime || 0) - target);
      if (!audio.paused && mtv.paused) mtv.play().catch(() => {});
      if (audio.paused && !mtv.paused) mtv.pause();
      if (drift > 0.45 && !mtv.seeking) {
        try {
          mtv.currentTime = Math.min(target, Math.max(0, mtv.duration - 0.05));
        } catch (err) {}
      }
    }
  }
  if (art) {
    const live = (!audio.paused || state.playerClockHold != null) && !!audio.src && !state.playerHeld;
    if (art.classList.contains("is-live") !== live) art.classList.toggle("is-live", live);
  }
  refreshPlayIcon();
  syncGuide(hold != null ? hold : undefined);
  const align = $("playerAlign");
  if (align && !align.hidden) api.ensureTimeline().sync(time, dur);
  // Keep the frame loop only while something can still change: playback, a
  // scrub, timeline editing, or a learn flow holding the clock.
  const running =
    !audio.paused ||
    hold != null ||
    document.body.classList.contains("edit-on") ||
    document.body.classList.contains("learn-on") ||
    (!!align && !align.hidden);
  state.playerRaf = running ? requestAnimationFrame(paintPlayer) : 0;
}

export function kickPlayerPaint() {
  if (state.playerRaf) return;
  const page = $("page-player");
  if (page && page.hidden) return;
  state.playerRaf = requestAnimationFrame(paintPlayer);
}

export function resetPlayerFace() {
  lastPaintAt = 0;
  lastNowText = "";
  lastLeftText = "";
  state.playerClockHold = null;
  state.playerClockHoldAt = 0;
  state.playerHoldDur = 0;
  state.selectedCue = 0;
  state.lyricPaint.prev = "";
  state.lyricPaint.cur = "";
  state.lyricPaint.next = "";
  state.lyricPaint.scroll = { prev: "", cur: "", next: "" };
  const scroll = $("playerLyricScroll");
  if (scroll) {
    scroll.textContent = "";
    scroll.dataset.windowKey = "";
    scroll.scrollTop = 0;
  }
  releasePlayerMtv();
  state.lyricPaint.align = "";
  ["playerPrev", "playerCur", "playerNext"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = "";
  });
  ["playerNow", "playerNowDock"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = "0:00";
  });
  ["playerLeft", "playerLeftDock"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = "−0:00";
  });
  ["playerSeek", "playerSeekDock"].forEach((id) => {
    const seek = $(id);
    if (!seek) return;
    seek.value = "0";
    seek.style.setProperty("--seek-p", "0%");
  });
}

registerPaintPlayer(paintPlayer);
