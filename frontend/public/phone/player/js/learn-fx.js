import { $ } from "../../../shared/ui/js/dom.js";
import { state } from "../../state.js";
import { ensurePhoneCtx } from "./mic.js";

export const SFX_GAIN = 0.068;
const COLORS = ["#f5c16c", "#ffe8bc", "#ff4d8d", "#ffffff", "#6ec8ff"];

/** @type {{ dots: LearnFxDot[], rings: LearnFxRing[], raf: number }} */
const fx = { dots: [], rings: [], raf: 0 };

function reduced() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function fxCtx() {
  const ctx = ensurePhoneCtx() || (state.playerHook && state.playerHook.ctx);
  if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

function canvas() {
  const el = $("learnFx");
  if (!el) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = el.clientWidth;
  const h = el.clientHeight;
  if (el.width !== Math.round(w * dpr) || el.height !== Math.round(h * dpr)) {
    el.width = Math.round(w * dpr);
    el.height = Math.round(h * dpr);
    const ctx = el.getContext("2d");
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  return el;
}

function originOf(el) {
  const layer = $("playerLearn");
  const a = el.getBoundingClientRect();
  const b = layer ? layer.getBoundingClientRect() : { left: 0, top: 0 };
  return { x: a.left - b.left + a.width / 2, y: a.top - b.top + a.height / 2 };
}

/** @param {number} x @param {number} y @param {"hit" | "line"} kind */
function spawnBurst(x, y, kind) {
  const n = kind === "line" ? 58 : 38;
  const speed = kind === "line" ? 9.4 : 7.2;
  for (let i = 0; i < n; i += 1) {
    const a = (i / n) * Math.PI * 2 + Math.random() * 0.28;
    const v = speed * (0.4 + Math.random() * 0.85);
    fx.dots.push({
      x,
      y,
      vx: Math.cos(a) * v,
      vy: Math.sin(a) * v - 1.6,
      life: 1,
      decay: 0.011 + Math.random() * 0.014,
      r: 2.1 + Math.random() * 3.4,
      color: COLORS[i % COLORS.length],
      star: i % 3 === 0,
    });
  }
  fx.rings.push({ x, y, r: 12, grow: kind === "line" ? 7.8 : 5.8, life: 1 });
  fx.rings.push({ x, y, r: 6, grow: kind === "line" ? 10 : 7.4, life: 1 });
}

function drawStar(g, x, y, r) {
  g.beginPath();
  for (let i = 0; i < 8; i += 1) {
    const rr = i % 2 ? r * 0.42 : r;
    const a = -Math.PI / 2 + (i * Math.PI) / 4;
    const px = x + Math.cos(a) * rr;
    const py = y + Math.sin(a) * rr;
    i ? g.lineTo(px, py) : g.moveTo(px, py);
  }
  g.closePath();
}

function tick() {
  const el = canvas();
  const g = el && el.getContext("2d");
  if (!g || !el) {
    fx.raf = 0;
    return;
  }
  g.clearRect(0, 0, el.clientWidth, el.clientHeight);
  fx.rings = fx.rings.filter((ring) => {
    ring.r += ring.grow;
    ring.life -= 0.045;
    if (ring.life <= 0) return false;
    g.beginPath();
    g.strokeStyle = `rgba(245,193,108,${0.72 * ring.life})`;
    g.lineWidth = 3.2 * ring.life;
    g.shadowColor = "rgba(245,193,108,.8)";
    g.shadowBlur = 12;
    g.arc(ring.x, ring.y, ring.r, 0, Math.PI * 2);
    g.stroke();
    g.shadowBlur = 0;
    return true;
  });
  fx.dots = fx.dots.filter((dot) => {
    dot.x += dot.vx;
    dot.y += dot.vy;
    dot.vy += 0.11;
    dot.vx *= 0.985;
    dot.life -= dot.decay;
    if (dot.life <= 0) return false;
    g.globalAlpha = Math.max(0, dot.life);
    g.fillStyle = dot.color;
    g.shadowColor = dot.color;
    g.shadowBlur = 10;
    if (dot.star) {
      drawStar(g, dot.x, dot.y, dot.r * 1.6);
      g.fill();
    } else {
      g.beginPath();
      g.arc(dot.x, dot.y, dot.r, 0, Math.PI * 2);
      g.fill();
    }
    g.shadowBlur = 0;
    g.globalAlpha = 1;
    return true;
  });
  if (fx.dots.length || fx.rings.length) {
    fx.raf = requestAnimationFrame(tick);
  } else {
    g.clearRect(0, 0, el.clientWidth, el.clientHeight);
    fx.raf = 0;
  }
}

function kickDraw() {
  if (!fx.raf) fx.raf = requestAnimationFrame(tick);
}

/** Quiet sparkle on a side bus. Never touches karaoke gain. */
function playOkSfx(kind) {
  const ctx = fxCtx();
  if (!ctx) return;
  const now = ctx.currentTime;
  const bus = ctx.createGain();
  bus.gain.setValueAtTime(SFX_GAIN, now);
  bus.connect(ctx.destination);
  const notes = kind === "line" ? [1318.5, 1760, 2093, 2637] : [1318.5, 1975.5, 2637];
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = i ? "sine" : "triangle";
    osc.frequency.setValueAtTime(freq, now);
    const t0 = now + i * 0.018;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.42 / (1 + i * 0.35), t0 + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.15 + i * 0.03);
    osc.connect(gain);
    gain.connect(bus);
    osc.start(t0);
    osc.stop(t0 + 0.2 + i * 0.03);
  });
}

function haptic() {
  try {
    if (navigator.vibrate) navigator.vibrate(12);
  } catch (err) {}
}

export function playMissSfx() {
  const ctx = fxCtx();
  if (!ctx) return;
  const now = ctx.currentTime;
  const bus = ctx.createGain();
  bus.gain.setValueAtTime(0.032, now);
  bus.connect(ctx.destination);
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(220, now);
  osc.frequency.exponentialRampToValueAtTime(140, now + 0.08);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.28, now + 0.008);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.09);
  osc.connect(gain);
  gain.connect(bus);
  osc.start(now);
  osc.stop(now + 0.1);
  try {
    if (navigator.vibrate) navigator.vibrate(8);
  } catch (err) {}
}

/**
 * @param {HTMLElement | null} el
 * @param {{ line?: boolean }} [opts]
 */
export function celebrateCorrect(el, opts) {
  const kind = opts && opts.line ? "line" : "hit";
  playOkSfx(kind);
  haptic();
  if (!el) return;
  el.classList.add("is-burst");
  window.setTimeout(() => el.classList.remove("is-burst"), 460);
  if (reduced()) return;
  const { x, y } = originOf(el);
  spawnBurst(x, y, kind);
  kickDraw();
}

let countGen = 0;

function playCountSfx(go) {
  const ctx = fxCtx();
  if (!ctx) return;
  const now = ctx.currentTime;
  const bus = ctx.createGain();
  bus.gain.setValueAtTime(go ? 0.055 : 0.04, now);
  bus.connect(ctx.destination);
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = go ? "triangle" : "sine";
  osc.frequency.setValueAtTime(go ? 784 : 523.25, now);
  if (go) osc.frequency.exponentialRampToValueAtTime(1174.7, now + 0.12);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.36, now + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + (go ? 0.22 : 0.1));
  osc.connect(gain);
  gain.connect(bus);
  osc.start(now);
  osc.stop(now + (go ? 0.24 : 0.12));
}

export function cancelCountdown() {
  countGen += 1;
  const wrap = $("learnCount");
  if (wrap) wrap.hidden = true;
}

export function runCountdown() {
  const gen = ++countGen;
  const wrap = $("learnCount");
  const num = $("learnCountNum");
  if (!wrap || !num) return Promise.resolve(true);
  wrap.hidden = false;
  const steps = reduced()
    ? [{ text: "GO", ms: 160 }]
    : [
      { text: "3", ms: 620 },
      { text: "2", ms: 620 },
      { text: "1", ms: 620 },
      { text: "GO", ms: 360 },
    ];
  return new Promise((resolve) => {
    let i = 0;
    const step = () => {
      if (gen !== countGen) {
        resolve(false);
        return;
      }
      if (i >= steps.length) {
        wrap.hidden = true;
        resolve(true);
        return;
      }
      const cur = steps[i];
      num.textContent = cur.text;
      wrap.classList.toggle("is-go", cur.text === "GO");
      num.classList.remove("is-pop");
      void num.offsetWidth;
      num.classList.add("is-pop");
      playCountSfx(cur.text === "GO");
      i += 1;
      window.setTimeout(step, cur.ms);
    };
    step();
  });
}

export function clearLearnFx() {
  cancelCountdown();
  fx.dots = [];
  fx.rings = [];
  if (fx.raf) cancelAnimationFrame(fx.raf);
  fx.raf = 0;
  const el = $("learnFx");
  const g = el && el.getContext("2d");
  if (g && el) g.clearRect(0, 0, el.width, el.height);
}
