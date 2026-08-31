import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { applyLyricMode, paintLine, cueIndexAt as cueIndexAtCues } from "../../../../shared/lyrics/js/paint.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { refreshPlayIcon, registerPaintPlayer, syncGuide } from "./controls.js";

export function cueIndexAt(time) {
  return cueIndexAtCues(state.playerLyrics.cues || [], time);
}

export function fmtClock(ms) {
  const n = Math.max(0, Math.floor((ms || 0) / 1000));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}

export function drawPlayerBands(time) {
  if (!state.playerViz) state.playerViz = LovBands.create($("playerBands"));
  const audio = $("playerAudio");
  if (audio && (audio.currentSrc || audio.src)) state.playerViz.setSource(audio.currentSrc || audio.src);
  const playing = !!(state.playerHook && audio && !audio.paused && audio.src);
  if (playing) LovBands.pull(state.playerHook);
  state.playerViz.draw({
    playing,
    freq: state.playerHook && state.playerHook.freq,
    wave: state.playerHook && state.playerHook.time,
    playMs: time || 0,
    duration: (audio.duration || 0) * 1000,
    cues: state.playerLyrics.cues || [],
    selected: state.selectedCue
  });
}

function playerIdleLyric() {
  return state.playerSong ? "" : t("phone.player.idle");
}

function paintPlayerScroll(cues, time, mode) {
  const list = $("playerLyricScroll");
  if (!list) return;
  const key = cues.map((cue) => `${cue.start_ms}:${cue.end_ms}:${cue.text || ""}`).join("|");
  if (list.dataset.cuesKey !== key) {
    list.textContent = "";
    list.dataset.cuesKey = key;
    list.dataset.activeIndex = "-1";
    state.lyricPaint.scroll = { prev: "", cur: "", next: "" };
    cues.forEach((cue, index) => {
      const row = document.createElement("div");
      row.className = "player-lyric-scroll-line line";
      row.dataset.cueIndex = String(index);
      list.appendChild(row);
    });
  }
  const active = cues.findIndex((cue) => time >= cue.start_ms && time < cue.end_ms);
  const upcoming = cues.findIndex((cue) => time < cue.start_ms);
  const index = active >= 0 ? active : upcoming >= 0 ? upcoming : cues.length - 1;
  cues.forEach((cue, cueIndex) => {
    const row = list.children[cueIndex];
    if (!row) return;
    const rowTime = cueIndex === active ? time : cueIndex < index ? 1e12 : -1;
    paintLine(row, cue, rowTime, `scroll:${cueIndex}`, state.lyricPaint.scroll, "", mode);
    row.classList.toggle("is-current", cueIndex === index);
  });
  if (String(index) !== (list.dataset.activeIndex || "-1")) {
    list.dataset.activeIndex = String(index);
    const current = list.children[index];
    if (current) {
      const target = Math.max(0, current.offsetTop - list.clientHeight * 0.62);
      if (typeof list.scrollTo === "function") list.scrollTo({ top: target, behavior: "smooth" });
      else list.scrollTop = target;
    }
  }
}

export function paintPlayer() {
  const page = $("page-player");
  if (page && page.hidden) {
    state.playerRaf = 0;
    return;
  }
  const audio = $("playerAudio");
  const hold = state.playerClockHold;
  const time = Math.floor((hold != null ? hold : audio.currentTime || 0) * 1000);
  const cues = state.playerLyrics.cues || [];
  const mode = applyLyricMode(document.body, state.lyricMode);
  const lyricsOnly = document.body.classList.contains("display-lyrics");
  const scroll = $("playerLyricScroll");
  if (scroll) scroll.hidden = !lyricsOnly;
  [$("playerPrev"), $("playerCur"), $("playerNext")].forEach((el) => {
    if (el) el.hidden = lyricsOnly;
  });
  if (lyricsOnly) paintPlayerScroll(cues, time, mode);
  const idx = cues.findIndex((c) => time >= c.start_ms && time < c.end_ms);
  const upcomingIdx = cues.findIndex((c) => time < c.start_ms);
  if (!lyricsOnly && idx >= 0) {
    paintLine($("playerPrev"), idx > 0 ? cues[idx - 1] : null, 1e12, "prev", state.lyricPaint, "", mode);
    paintLine($("playerCur"), cues[idx], time, "cur", state.lyricPaint, "", mode);
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
  drawPlayerBands(time);
  const durSec = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : state.playerHoldDur;
  const dur = (durSec || 0) * 1000;
  $("playerNow").textContent = fmtClock(time);
  $("playerLeft").textContent = dur ? `−${fmtClock(Math.max(0, dur - time))}` : "−0:00";
  const seek = $("playerSeek");
  if (seek) {
    const ratio = durSec ? Math.max(0, Math.min(1, time / 1000 / durSec)) : 0;
    if (!seek.matches(":active") && durSec) seek.value = String(Math.round(ratio * 1000));
    seek.style.setProperty("--seek-p", `${(seek.matches(":active") ? Number(seek.value) / 1000 : ratio) * 100}%`);
  }
  const art = $("playerArt");
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
  state.lyricPaint.align = "";
  ["playerPrev", "playerCur", "playerNext"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = "";
  });
  const now = $("playerNow");
  const left = $("playerLeft");
  if (now) now.textContent = "0:00";
  if (left) left.textContent = "−0:00";
  const seek = $("playerSeek");
  if (seek) {
    seek.value = "0";
    seek.style.setProperty("--seek-p", "0%");
  }
  if (state.playerViz) state.playerViz.draw({ playing: false, playMs: 0, duration: 0, cues: [], selected: 0 });
}

registerPaintPlayer(paintPlayer);
