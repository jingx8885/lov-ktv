import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { hookPlayerAudio } from "../playback/controls.js";
import {
  cancelCueWindow,
  cancelLineHold,
  confirmLineHold,
  holdAfterLine,
  isLineHold,
  needsLineHold,
  paintLearnLine,
  playCueWindow
} from "./play.js";
import { celebrateCorrect, playMissSfx } from "./fx.js";

const TILE_SKINS = [
  { bg: "rgba(255, 77, 141, .38)", line: "#ff4d8d", ink: "#ffe7f1" },
  { bg: "rgba(245, 193, 108, .38)", line: "#f5c16c", ink: "#fff6df" },
  { bg: "rgba(110, 200, 255, .36)", line: "#6ec8ff", ink: "#e7f6ff" },
  { bg: "rgba(180, 140, 255, .38)", line: "#b48cff", ink: "#f3ebff" },
  { bg: "rgba(72, 220, 160, .34)", line: "#48dca0", ink: "#dcfff2" },
  { bg: "rgba(255, 120, 80, .36)", line: "#ff7850", ink: "#ffe8e0" }
];

/** @type {StageFxHandle | null} */
let tapFx = null;
let tapFxRaf = 0;

/** @type {LearnTapSession & { done: Set<number> }} */
const session = {
  lines: [],
  index: 0,
  cursor: 0,
  running: false,
  hits: 0,
  misses: 0,
  combo: 0,
  maxCombo: 0,
  perfect: 0,
  lineMisses: 0,
  done: new Set(),
  jump: -1
};
let tapSync = 0;

/** @param {LearnLine[]} lines */
export function resetTap(lines) {
  session.lines = (lines || []).filter((line) => line.words && line.words.length);
  session.index = 0;
  session.cursor = 0;
  session.running = false;
  session.hits = 0;
  session.misses = 0;
  session.combo = 0;
  session.maxCombo = 0;
  session.perfect = 0;
  session.lineMisses = 0;
  session.done = new Set();
  session.jump = -1;
}

export function tapBusy() {
  return session.running;
}

function currentLine() {
  return session.lines[session.index];
}

function lineAt(ms) {
  for (let i = 0; i < session.lines.length; i += 1) {
    if (ms >= session.lines[i].start_ms && ms < session.lines[i].end_ms) return i;
  }
  return -1;
}

function paintClock(ms) {
  const list = session.lines;
  const bar = $("learnTapBar");
  if (!bar || !list.length) return;
  const start = list[0].start_ms;
  const end = list[list.length - 1].end_ms;
  const pct = end > start ? Math.max(0, Math.min(1, (ms - start) / (end - start))) : 0;
  bar.style.width = `${Math.round(pct * 100)}%`;
}

function paintProgress() {
  const total = session.lines.length;
  const idx = Math.max(0, session.index);
  $("learnTitle").textContent = t("learn.tap");
  $("learnMeta").textContent = total ? `${idx + 1} / ${total}` : "";
  $("learnTapCombo").textContent = session.running ? `COMBO ${session.combo}` : t("learn.tapHintLine");
}

function paintHint(line) {
  paintLearnLine({
    src: "learnTapSrc",
    roma: "learnTapRoma",
    zh: "learnTapZh",
    text: line ? line.text : "",
    romaji: line ? line.romaji : "",
    zhText: (line && (line.translation || line.zh)) || ""
  });
}

function appendStrip(text) {
  const strip = $("learnTapStrip");
  if (!strip) return;
  const chip = document.createElement("span");
  chip.className = "learn-tap-got";
  chip.textContent = text;
  strip.appendChild(chip);
  strip.scrollLeft = strip.scrollWidth;
}

function clearBoard() {
  const field = $("learnTapField");
  const strip = $("learnTapStrip");
  if (field) field.innerHTML = "";
  if (strip) strip.innerHTML = "";
}

function overlaps(a, b, gap) {
  return !(
    a.left + a.w + gap < b.left ||
    b.left + b.w + gap < a.left ||
    a.top + a.h + gap < b.top ||
    b.top + b.h + gap < a.top
  );
}

function tileBox(text) {
  const len = Math.max(1, Array.from(text || "").length);
  return {
    w: Math.min(156, Math.max(58, 32 + len * 20 + Math.random() * 18)),
    h: 50 + (Math.random() < 0.4 ? 10 : 0)
  };
}

function shuffle(list) {
  const out = list.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = out[i];
    out[i] = out[j];
    out[j] = tmp;
  }
  return out;
}

/** @param {LearnWord[]} words @param {HTMLElement} field */
function scatterTiles(words, field) {
  const viewW = field.clientWidth || 320;
  const viewH = Math.max(field.clientHeight || 280, 220);
  const pad = 8;
  const skins = shuffle(TILE_SKINS);
  const placed = [];
  words.forEach((word, i) => {
    const size = tileBox(word.text);
    let box = null;
    for (let tryN = 0; tryN < 48; tryN += 1) {
      const next = {
        left: pad + Math.random() * Math.max(12, viewW - size.w - pad * 2),
        top: pad + Math.random() * Math.max(12, viewH - size.h - pad * 2),
        w: size.w,
        h: size.h
      };
      if (!placed.some((item) => overlaps(next, item, 12))) {
        box = next;
        break;
      }
    }
    if (!box) {
      box = {
        left: pad + ((i * 73) % Math.max(12, viewW - size.w - pad)),
        top: pad + ((i * 97) % Math.max(12, viewH - size.h - pad)),
        w: size.w,
        h: size.h
      };
    }
    placed.push({
      ...box,
      rot: (Math.random() - 0.5) * 22,
      bob: -(6 + Math.random() * 10),
      delay: Math.floor(Math.random() * 1200),
      dur: 2.2 + Math.random() * 1.8,
      skin: skins[i % skins.length]
    });
  });
  return placed;
}

function tapBeat() {
  const hook = state.playerHook;
  if (!hook) return 0;
  const wave = hook.time;
  const freq = hook.freq;
  let peak = 0;
  let sum = 0;
  if (wave && wave.length) {
    const step = Math.max(1, Math.floor(wave.length / 120));
    for (let i = 0; i < wave.length; i += step) {
      const value = (wave[i] - 128) / 128;
      sum += value * value;
      peak = Math.max(peak, Math.abs(value));
    }
    return Math.max(0, Math.min(1, Math.sqrt(sum / Math.max(1, Math.floor(wave.length / step))) * 0.75 + peak * 0.5));
  }
  if (freq && freq.length) {
    for (let i = 2; i < Math.min(40, freq.length); i += 1) sum += freq[i];
    return Math.max(0, Math.min(1, sum / 38 / 255));
  }
  return 0;
}

function ensureTapFx() {
  if (tapFx || !window.LovStageFxRuntime) return tapFx;
  const canvas = $("learnTapFx");
  if (!canvas) return null;
  tapFx = LovStageFxRuntime.create(canvas);
  return tapFx;
}

function kickTapFx() {
  hookPlayerAudio();
  if (tapFxRaf) return;
  const tick = () => {
    tapFxRaf = 0;
    const pane = $("learnTap");
    if (!pane || pane.hidden) return;
    const handle = ensureTapFx();
    if (handle) handle.draw({ beat: tapBeat() });
    tapFxRaf = requestAnimationFrame(tick);
  };
  tapFxRaf = requestAnimationFrame(tick);
}

function burstTapFx() {
  const handle = ensureTapFx();
  if (handle) handle.spawn();
}

function stopTapFx() {
  if (tapFxRaf) cancelAnimationFrame(tapFxRaf);
  tapFxRaf = 0;
  if (tapFx) tapFx.clear();
}

/** @param {LearnLine} line */
function spawnTiles(line) {
  const field = $("learnTapField");
  const strip = $("learnTapStrip");
  if (!field) return;
  field.innerHTML = "";
  if (strip) strip.innerHTML = "";
  const words = line.words || [];
  const slots = scatterTiles(words, field);
  burstTapFx();
  words.forEach((word, i) => {
    const slot = slots[i];
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "learn-tap-tile";
    tile.dataset.i = String(i);
    tile.dataset.text = word.text;
    tile.style.left = `${Math.max(4, slot.left)}px`;
    tile.style.top = `${Math.max(4, slot.top)}px`;
    tile.style.width = `${slot.w}px`;
    tile.style.setProperty("--tile-bg", slot.skin.bg);
    tile.style.setProperty("--tile-line", slot.skin.line);
    tile.style.setProperty("--tile-ink", slot.skin.ink);
    tile.style.setProperty("--tile-rot", `${slot.rot}deg`);
    tile.style.setProperty("--tile-bob", `${slot.bob}px`);
    tile.style.setProperty("--float-delay", `${slot.delay}ms`);
    tile.style.setProperty("--float-dur", `${slot.dur}s`);
    tile.innerHTML = `<b>${escapeHtml(word.text)}</b>${word.romaji ? `<small>${escapeHtml(word.romaji)}</small>` : ""}`;
    tile.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      onTap(tile);
    });
    field.appendChild(tile);
  });
}

/** @param {HTMLButtonElement} tile */
function onTap(tile) {
  if (!session.running || tile.classList.contains("is-hit")) return;
  const idx = Number(tile.dataset.i);
  if (idx === session.cursor) {
    session.cursor += 1;
    session.hits += 1;
    session.combo += 1;
    session.maxCombo = Math.max(session.maxCombo, session.combo);
    tile.classList.add("is-hit");
    tile.setAttribute("aria-disabled", "true");
    appendStrip(tile.dataset.text || "");
    const line = currentLine();
    const last = line && session.cursor === (line.words || []).length;
    celebrateCorrect(tile, { line: !!last });
    paintProgress();
    return;
  }
  session.combo = 0;
  session.misses += 1;
  session.lineMisses += 1;
  tile.classList.remove("is-miss");
  void tile.offsetWidth;
  tile.classList.add("is-miss");
  window.setTimeout(() => tile.classList.remove("is-miss"), 240);
  playMissSfx();
  paintProgress();
}

function markLeftovers() {
  const field = $("learnTapField");
  if (!field) return;
  field.querySelectorAll(".learn-tap-tile:not(.is-hit)").forEach((tile) => {
    tile.classList.add("is-left");
    tile.setAttribute("aria-disabled", "true");
  });
}

function paintTapLine() {
  const line = currentLine();
  paintProgress();
  paintHint(line);
}

function finishLine(index) {
  if (session.done.has(index)) return;
  const line = session.lines[index];
  if (!line) return;
  session.done.add(index);
  const cursor = index === session.index ? session.cursor : 0;
  const left = Math.max(0, (line.words || []).length - cursor);
  if (left) {
    session.misses += left;
    session.combo = 0;
    session.lineMisses += left;
    if (index === session.index) markLeftovers();
  } else if ((line.words || []).length) {
    session.perfect += 1;
  }
}

function enterLine(index) {
  if (index < 0 || session.done.has(index)) return;
  session.index = index;
  session.cursor = 0;
  session.lineMisses = 0;
  paintTapLine();
  spawnTiles(session.lines[index]);
}

function onClock(ms) {
  if (!session.running) return;
  session.lines.forEach((line, i) => {
    if (ms >= line.end_ms) finishLine(i);
  });
  const idx = lineAt(ms);
  if (idx >= 0 && idx !== session.index && !session.done.has(idx)) enterLine(idx);
  paintClock(ms);
  paintProgress();
}

function startTapClock() {
  const audio = $("playerAudio");
  const tick = () => {
    if (!session.running) {
      tapSync = 0;
      return;
    }
    onClock(((audio && audio.currentTime) || 0) * 1000);
    tapSync = requestAnimationFrame(tick);
  };
  if (tapSync) cancelAnimationFrame(tapSync);
  tapSync = requestAnimationFrame(tick);
}

function stopTapClock() {
  if (tapSync) cancelAnimationFrame(tapSync);
  tapSync = 0;
}

export function paintTapHome() {
  session.index = 0;
  paintProgress();
  paintClock(0);
  paintHint(null);
  clearBoard();
  $("learnTapCombo").textContent = t("learn.tapHintLine");
  $("learnTapSkip").textContent = t("learn.skip");
  $("learnTapSkip").disabled = true;
  if ($("learnTapNext")) $("learnTapNext").hidden = true;
  kickTapFx();
  burstTapFx();
}

export async function runTap() {
  if (session.running) return null;
  if (!session.lines.length) {
    showToast(t("learn.noWords"));
    return null;
  }
  session.running = true;
  session.hits = 0;
  session.misses = 0;
  session.combo = 0;
  session.maxCombo = 0;
  session.perfect = 0;
  session.done = new Set();
  session.index = -1;
  session.jump = -1;
  $("learnTapSkip").disabled = false;
  $("learnTapSkip").textContent = t("learn.skip");
  const list = session.lines;
  enterLine(0);
  try {
    startTapClock();
    if (!needsLineHold()) {
      const playing = playCueWindow(list[0].start_ms, list[list.length - 1].end_ms, { vocal: true });
      await playing;
    } else {
      for (let i = 0; i < list.length; i += 1) {
        if (!session.running) return null;
        if (session.jump >= 0) {
          i = session.jump;
          session.jump = -1;
        }
        enterLine(i);
        const line = list[i];
        const played = await playCueWindow(line.start_ms, line.end_ms, { vocal: true });
        if (!session.running) return null;
        finishLine(i);
        if (session.jump >= 0) continue;
        if (!played) return null;
        if (i < list.length - 1) {
          const go = await holdAfterLine({ button: $("learnTapNext"), restore: t("learn.next") });
          if (!session.running) return null;
          if (session.jump >= 0) continue;
          if (!go) return null;
        }
      }
    }
    if (!session.running) return null;
    onClock(list[list.length - 1].end_ms);
    const bar = $("learnTapBar");
    if (bar) bar.style.width = "100%";
    const total = session.hits + session.misses;
    const pct = total ? Math.round((session.hits / total) * 100) : 0;
    return {
      pct,
      hits: session.hits,
      misses: session.misses,
      maxCombo: session.maxCombo,
      perfect: session.perfect,
      total: session.lines.length
    };
  } finally {
    session.running = false;
    session.jump = -1;
    stopTapClock();
    cancelLineHold();
    $("learnTapSkip").textContent = t("learn.skip");
    $("learnTapSkip").disabled = true;
    if ($("learnTapNext")) $("learnTapNext").hidden = true;
  }
}

export function skipTapLine() {
  const list = session.lines;
  if (!session.running || !list.length) return;
  if (isLineHold()) {
    confirmLineHold();
    return;
  }
  const audio = $("playerAudio");
  const ms = ((audio && audio.currentTime) || 0) * 1000;
  const live = lineAt(ms);
  const idx = live >= 0 ? live : Math.max(0, session.index);
  finishLine(idx);
  if (needsLineHold()) {
    session.jump = idx + 1;
    cancelCueWindow();
    return;
  }
  const next = list[idx + 1];
  try {
    if (audio) audio.currentTime = (next ? next.start_ms : list[idx].end_ms) / 1000;
  } catch (err) {}
}

export function stopTap() {
  session.running = false;
  stopTapClock();
  cancelLineHold();
  cancelCueWindow();
  stopTapFx();
}

/** @param {LearnQuiz} pack */
export function startTap(pack) {
  resetTap(pack.lines);
  paintTapHome();
}

/** @param {any} score @param {(pct: number) => string} grade */
export function tapScoreView(score, grade) {
  const tried = (score.hits || 0) + (score.misses || 0);
  return {
    title: t("learn.score.tap"),
    again: t("learn.again.tap"),
    sub: t("learn.score.tapped", { grade: grade(score.pct), hits: score.hits || 0, tried }),
    detail: t("learn.score.tapHint", {
      combo: score.maxCombo || 0,
      perfect: score.perfect || 0,
      total: score.total || 0
    }),
    celebrate: score.pct >= 70
  };
}

export function bindTap() {
  $("learnTapSkip").onclick = () => skipTapLine();
  if ($("learnTapNext")) $("learnTapNext").onclick = () => confirmLineHold();
}
