import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { paintLine, cueIndexAt as cueIndexAtCues } from "../../../../shared/lyrics/js/paint.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { refreshPlayIcon, registerPaintPlayer, syncGuide } from "./controls.js";

let lastPaintAt = 0;
// The scroll view is painted on every animation frame while lyrics-only mode
// is active.  Keep the expensive source fingerprint out of that hot path:
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

function paintPlayerScroll(cues, time, mode) {
  const list = $("playerLyricScroll");
  if (!list) return;
  if (cues !== scrollCuesRef) {
    scrollCuesRef = cues;
    scrollCuesKey = cues.map((cue) => `${cue.start_ms}:${cue.end_ms}:${cue.text || ""}`).join("|");
  }
  const key = scrollCuesKey;
  const modeChanged = list.dataset.lyricMode !== mode;
  let rebuilt = false;
  if (list.dataset.cuesKey !== key) {
    rebuilt = true;
    list.textContent = "";
    list.dataset.cuesKey = key;
    list.dataset.activeIndex = "-1";
    const fragment = document.createDocumentFragment();
    cues.forEach((cue, index) => {
      const row = document.createElement("div");
      row.className = "player-lyric-scroll-line line";
      row.dataset.cueIndex = String(index);
      row.textContent = mode === "zh" ? String(cue.zh || cue.text || "") : String(cue.text || "");
      fragment.appendChild(row);
    });
    list.appendChild(fragment);
  } else if (modeChanged) {
    // Changing ja/zh/roma/all should not throw away hundreds of rows.  Reset
    // their lightweight text placeholders; only the visible/active rows are
    // expanded by paintLine below.
    for (let index = 0; index < cues.length; index += 1) {
      const row = list.children[index];
      if (row)
        row.textContent =
          mode === "zh" ? String(cues[index].zh || cues[index].text || "") : String(cues[index].text || "");
    }
  }
  list.dataset.lyricMode = mode;
  if (rebuilt || modeChanged) state.lyricPaint.scroll = { prev: "", cur: "", next: "" };
  const lyricTime = lyricClockMs(time);
  const active = cues.findIndex((cue) => lyricTime >= cue.start_ms && lyricTime < cue.end_ms);
  const upcoming = cues.findIndex((cue) => lyricTime < cue.start_ms);
  const index = active >= 0 ? active : upcoming >= 0 ? upcoming : cues.length - 1;
  const previous = Number(list.dataset.activeIndex || -1);
  if (rebuilt || modeChanged) {
    cues.forEach((cue, cueIndex) => {
      if (cueIndex !== index && Math.abs(cueIndex - index) > 10) return;
      const row = list.children[cueIndex];
      if (!row) return;
      const rowTime = cueIndex === active ? lyricTime : cueIndex < index ? 1e12 : -1;
      paintLine(row, cue, rowTime, `scroll:${cueIndex}`, state.lyricPaint.scroll, "", mode);
      row.classList.toggle("is-current", cueIndex === index);
    });
    list.dataset.activeIndex = String(index);
    const current = list.children[index];
    if (current && (rebuilt || previous !== index)) {
      const target = Math.max(0, current.offsetTop - list.clientHeight * 0.62);
      if (typeof list.scrollTo === "function") list.scrollTo({ top: target, behavior: "auto" });
      else list.scrollTop = target;
    }
  } else if (previous !== index) {
    if (previous >= 0 && cues[previous] && list.children[previous]) {
      paintLine(list.children[previous], cues[previous], 1e12, `scroll:${previous}`, state.lyricPaint.scroll, "", mode);
      list.children[previous].classList.remove("is-current");
    }
    if (index >= 0 && cues[index] && list.children[index]) {
      paintLine(
        list.children[index],
        cues[index],
        index === active ? lyricTime : -1,
        `scroll:${index}`,
        state.lyricPaint.scroll,
        "",
        mode
      );
      list.children[index].classList.add("is-current");
    }
    list.dataset.activeIndex = String(index);
    const current = list.children[index];
    if (current) {
      const target = Math.max(0, current.offsetTop - list.clientHeight * 0.62);
      if (typeof list.scrollTo === "function") list.scrollTo({ top: target, behavior: "smooth" });
      else list.scrollTop = target;
    }
  } else if (active >= 0 && list.children[active]) {
    // Karaoke fill is the only part that changes every frame.
    paintLine(list.children[active], cues[active], lyricTime, `scroll:${active}`, state.lyricPaint.scroll, "", mode);
  }
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
  if (scroll) scroll.hidden = !lyricsOnly;
  [$("playerPrev"), $("playerCur"), $("playerNext")].forEach((el) => {
    if (el) el.hidden = lyricsOnly;
  });
  if (lyricsOnly) paintPlayerScroll(cues, time, mode);
  const lyricTime = lyricClockMs(time);
  const idx = cues.findIndex((c) => lyricTime >= c.start_ms && lyricTime < c.end_ms);
  const upcomingIdx = cues.findIndex((c) => lyricTime < c.start_ms);
  if (!lyricsOnly && idx >= 0) {
    paintLine($("playerPrev"), idx > 0 ? cues[idx - 1] : null, 1e12, "prev", state.lyricPaint, "", mode);
    paintLine($("playerCur"), cues[idx], lyricTime, "cur", state.lyricPaint, "", mode);
    paintLine($("playerNext"), cues[idx + 1] || null, -1, "next", state.lyricPaint, "", mode);
  } else if (!lyricsOnly && upcomingIdx >= 0) {
    const held = upcomingIdx > 0 ? cues[upcomingIdx - 1] : null;
    paintLine(
      $("playerPrev"),
      upcomingIdx > 1 ? cues[upcomingIdx - 2] : null,
      1e12,
      "prev",
      state.lyricPaint,
      "",
      mode
    );
    paintLine($("playerCur"), held, held ? 1e12 : 0, "cur", state.lyricPaint, "", mode);
    paintLine($("playerNext"), cues[upcomingIdx], -1, "next", state.lyricPaint, "", mode);
  } else if (!lyricsOnly) {
    paintLine($("playerPrev"), cues.length ? cues[cues.length - 1] : null, 1e12, "prev", state.lyricPaint, "", mode);
    paintLine($("playerCur"), null, 0, "cur", state.lyricPaint, playerIdleLyric(), mode);
    paintLine($("playerNext"), null, 0, "next", state.lyricPaint, "", mode);
  }
  const dragging = !!(state.alignTl && state.alignTl.isDragging());
  const nextSel = cueIndexAt(time);
  if (nextSel !== state.selectedCue && !dragging) state.selectedCue = nextSel;
  if (document.body.classList.contains("edit-on")) api.updateAlignNow(time);
  const durSec = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : state.playerHoldDur;
  const dur = (durSec || 0) * 1000;
  const nowText = fmtClock(time);
  const leftText = dur ? `−${fmtClock(Math.max(0, dur - time))}` : "−0:00";
  ["playerNow", "playerNowDock"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = nowText;
  });
  ["playerLeft", "playerLeftDock"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = leftText;
  });
  ["playerSeek", "playerSeekDock"].forEach((id) => {
    const seek = $(id);
    if (!seek) return;
    const ratio = durSec ? Math.max(0, Math.min(1, time / 1000 / durSec)) : 0;
    if (!seek.matches(":active") && durSec) seek.value = String(Math.round(ratio * 1000));
    seek.style.setProperty("--seek-p", `${(seek.matches(":active") ? Number(seek.value) / 1000 : ratio) * 100}%`);
  });
  const mtv = $("playerMtv");
  const art = $("playerArt");
  if (mtv) {
    const showMtv = document.body.classList.contains("display-mv") && !!mtv.src;
    const hasMtv = !!mtv.src;
    mtv.hidden = !showMtv;
    if (art) art.classList.toggle("has-mtv", showMtv);
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
  if (art)
    art.classList.toggle(
      "is-live",
      (!audio.paused || state.playerClockHold != null) && !!audio.src && !state.playerHeld
    );
  refreshPlayIcon();
  syncGuide(hold != null ? hold : undefined);
  const align = $("playerAlign");
  if (align && !align.hidden) api.ensureTimeline().sync(time, dur);
  state.playerRaf = requestAnimationFrame(paintPlayer);
}

export function kickPlayerPaint() {
  if (state.playerRaf) return;
  const page = $("page-player");
  if (page && page.hidden) return;
  state.playerRaf = requestAnimationFrame(paintPlayer);
}

export function resetPlayerFace() {
  lastPaintAt = 0;
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
    scroll.dataset.cuesKey = "";
    scroll.dataset.activeIndex = "-1";
    scroll.scrollTop = 0;
  }
  const mtv = $("playerMtv");
  if (mtv) {
    mtv.pause();
    mtv.removeAttribute("src");
    mtv.load();
  }
  const art = $("playerArt");
  if (art) art.classList.remove("has-mtv");
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
