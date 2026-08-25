(function (global) {
  "use strict";

  const EFFECTS = [
    "rings", "poly", "spiral", "rays", "confetti", "zigzag",
    "pop", "cross", "orbit", "wave", "stars", "grid",
  ];
  const C = { amber: "#f5c16c", gray: "rgba(244,241,234,.55)", ink: "rgba(11,16,32,.0)" };
  const ACCENTS = ["#ff4d8d", "#6ec8ff", "#ffffff"];
  const FX_IN = 0.55;
  const FX_OUT = 0.4;
  const MAX_LAYERS = 4;

  function mulberry32(a) {
    return function () {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
  const smooth = (t) => t * t * (3 - 2 * t);
  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
  const easeOutBack = (t) => {
    const c = 1.70158;
    const u = t - 1;
    return 1 + (c + 1) * u * u * u + c * u * u;
  };
  const easeOutElastic = (t) =>
    t <= 0 ? 0 : t >= 1 ? 1 : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
  const prog = (t, delay, dur) => clamp01((t - delay) / (dur == null ? FX_IN : dur));

  function pickColor(rng) {
    const r = rng();
    if (r < 0.62) return C.amber;
    if (r < 0.9) return C.gray;
    return ACCENTS[(rng() * ACCENTS.length) | 0];
  }

  function tracePoly(g, x, y, r, sides, rot) {
    g.beginPath();
    for (let i = 0; i < sides; i += 1) {
      const a = rot + (i * 2 * Math.PI) / sides;
      const px = x + Math.cos(a) * r;
      const py = y + Math.sin(a) * r;
      i ? g.lineTo(px, py) : g.moveTo(px, py);
    }
    g.closePath();
  }

  function traceStar(g, x, y, r, points, rot) {
    g.beginPath();
    for (let i = 0; i < points * 2; i += 1) {
      const rr = i % 2 ? r * 0.46 : r;
      const a = rot + (i * Math.PI) / points;
      const px = x + Math.cos(a) * rr;
      const py = y + Math.sin(a) * rr;
      i ? g.lineTo(px, py) : g.moveTo(px, py);
    }
    g.closePath();
  }

  function drawPiece(g, kind, color, x, y, r, rot) {
    if (r <= 0) return;
    g.save();
    g.translate(x, y);
    g.rotate(rot || 0);
    switch (kind) {
      case "circle":
        g.fillStyle = color;
        g.beginPath();
        g.arc(0, 0, r, 0, 7);
        g.fill();
        break;
      case "ring":
        g.strokeStyle = color;
        g.lineWidth = Math.max(2, r * 0.3);
        g.beginPath();
        g.arc(0, 0, r, 0, 7);
        g.stroke();
        break;
      case "square":
        g.fillStyle = color;
        g.fillRect(-r, -r, r * 2, r * 2);
        break;
      case "triangle":
        g.fillStyle = color;
        tracePoly(g, 0, 0, r * 1.2, 3, -Math.PI / 2);
        g.fill();
        break;
      case "diamond":
        g.fillStyle = color;
        tracePoly(g, 0, 0, r * 1.15, 4, 0);
        g.fill();
        break;
      case "hexagon":
        g.fillStyle = color;
        tracePoly(g, 0, 0, r * 1.1, 6, 0);
        g.fill();
        break;
      case "star":
        g.fillStyle = color;
        traceStar(g, 0, 0, r * 1.25, 5, -Math.PI / 2);
        g.fill();
        break;
      case "cross": {
        g.fillStyle = color;
        const w = r * 0.62;
        g.fillRect(-r, -w / 2, r * 2, w);
        g.fillRect(-w / 2, -r, w, r * 2);
        break;
      }
      default:
        break;
    }
    g.restore();
  }

  function strokePartial(g, pts, lens, vis) {
    g.beginPath();
    g.moveTo(pts[0].x, pts[0].y);
    let acc = 0;
    for (let i = 1; i < pts.length; i += 1) {
      const seg = lens[i - 1];
      if (acc + seg <= vis) {
        g.lineTo(pts[i].x, pts[i].y);
        acc += seg;
      } else {
        const f = seg > 0 ? (vis - acc) / seg : 0;
        const tx = pts[i - 1].x + (pts[i].x - pts[i - 1].x) * f;
        const ty = pts[i - 1].y + (pts[i].y - pts[i - 1].y) * f;
        g.lineTo(tx, ty);
        return { x: tx, y: ty };
      }
    }
    return pts[pts.length - 1];
  }

  function makeBuild() {
    return {
      rings(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        for (let i = 0; i < 7; i += 1) {
          inst.shapes.push({
            delay: i * 0.05,
            rEnd: minD * (0.13 + rng() * 0.29),
            w: 5 + rng() * 9,
            color: pickColor(rng),
          });
        }
        inst.dotR = minD * 0.07;
      },
      poly(inst, rng, fxW, fxH) {
        const sides = 3 + ((rng() * 5) | 0);
        const minD = Math.min(fxW, fxH);
        [
          [0.46, C.amber, 0],
          [0.3, C.gray, 0.09],
          [0.17, C.amber, 0.18],
        ].forEach(([s, color, d], i) => {
          inst.shapes.push({
            sides,
            delay: d,
            color,
            rEnd: minD * s,
            w: minD * (0.034 - i * 0.007),
          });
        });
      },
      spiral(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        for (let i = 0; i < 36; i += 1) {
          inst.shapes.push({
            ang: i * 0.55,
            rad: 6 + i * minD * 0.0125,
            size: minD * (0.009 + i * 0.0008),
            delay: i * 0.018,
            color: pickColor(rng),
          });
        }
      },
      rays(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        const n = 13 + ((rng() * 4) | 0);
        inst.r0 = minD * 0.06;
        for (let i = 0; i < n; i += 1) {
          inst.shapes.push({
            ang: (i / n) * 2 * Math.PI + rng() * 0.15,
            w: 0.09 + rng() * 0.13,
            len: minD * (0.36 + rng() * 0.1),
            delay: rng() * 0.12,
            color: rng() < 0.12 ? ACCENTS[(rng() * 3) | 0] : i % 2 ? C.gray : C.amber,
          });
        }
      },
      confetti(inst, rng, fxW, fxH) {
        const maxD = Math.hypot(fxW, fxH);
        const minD = Math.min(fxW, fxH);
        const kinds = ["square", "circle", "triangle", "diamond"];
        for (let i = 0; i < 30; i += 1) {
          inst.shapes.push({
            ang: rng() * 2 * Math.PI,
            dist: maxD * (0.12 + rng() * 0.46),
            size: minD * (0.026 + rng() * 0.05),
            spin: inst.dir * (1 + rng() * 2) * 2.2,
            delay: rng() * 0.18,
            kind: kinds[(rng() * 4) | 0],
            color: pickColor(rng),
          });
        }
      },
      zigzag(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        const horiz = rng() < 0.5;
        const n = 5 + ((rng() * 3) | 0);
        const pts = [];
        for (let i = 0; i <= n; i += 1) {
          const f = i / n;
          if (horiz) {
            pts.push({
              x: -fxW * 0.08 + f * fxW * 1.16,
              y: fxH * (i % 2 ? 0.72 + rng() * 0.14 : 0.14 + rng() * 0.14),
            });
          } else {
            pts.push({
              x: fxW * (i % 2 ? 0.7 + rng() * 0.16 : 0.14 + rng() * 0.16),
              y: -fxH * 0.08 + f * fxH * 1.16,
            });
          }
        }
        const lens = [];
        let total = 0;
        for (let i = 1; i < pts.length; i += 1) {
          const l = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
          lens.push(l);
          total += l;
        }
        inst.shapes.push({ pts, lens, total, w: minD * (0.026 + rng() * 0.024), color: C.amber });
      },
      pop(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        const kinds = ["circle", "square", "ring", "triangle", "hexagon"];
        for (let i = 0; i < 16; i += 1) {
          inst.shapes.push({
            x: fxW * (0.06 + rng() * 0.88),
            y: fxH * (0.06 + rng() * 0.88),
            size: minD * (0.036 + rng() * 0.06),
            delay: rng() * 0.28,
            rot: rng() * Math.PI,
            kind: kinds[(rng() * kinds.length) | 0],
            color: pickColor(rng),
          });
        }
      },
      cross(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        const size = minD * (0.6 + rng() * 0.25);
        inst.shapes.push({
          size,
          w: size * (0.14 + rng() * 0.08),
          color: rng() < 0.2 ? ACCENTS[(rng() * 3) | 0] : C.amber,
        });
      },
      orbit(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        const kinds = ["circle", "square", "triangle", "ring"];
        for (let i = 0; i < 10; i += 1) {
          inst.shapes.push({
            ang0: (i / 10) * 2 * Math.PI,
            rad: minD * (0.18 + rng() * 0.24),
            speed: inst.dir * (0.45 + rng() * 0.5),
            size: minD * (0.026 + rng() * 0.032),
            delay: rng() * 0.15,
            kind: kinds[i % 4],
            color: pickColor(rng),
          });
        }
        inst.coreR = minD * 0.055;
      },
      wave(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        for (let i = 0; i < 4; i += 1) {
          inst.shapes.push({
            y0: fxH * (0.14 + i * 0.24) + (rng() - 0.5) * fxH * 0.08,
            amp: minD * (0.03 + rng() * 0.05),
            wl: fxW * (0.45 + rng() * 0.4),
            speed: inst.dir * (1 + rng() * 1.2),
            th: minD * (0.07 + rng() * 0.06),
            side: i % 2 ? 1 : -1,
            delay: i * 0.08,
            color: rng() < 0.12 ? ACCENTS[(rng() * 3) | 0] : i % 2 ? C.gray : C.amber,
          });
        }
      },
      stars(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        for (let i = 0; i < 12; i += 1) {
          inst.shapes.push({
            x: fxW * (0.07 + rng() * 0.86),
            y: fxH * (0.07 + rng() * 0.86),
            r: minD * (0.034 + rng() * 0.055),
            delay: rng() * 0.25,
            rot: rng() * Math.PI,
            color: pickColor(rng),
          });
        }
      },
      grid(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        const n = 11;
        const radius = minD * (0.4 + rng() * 0.04);
        const lines = [];
        for (let i = 0; i < n; i += 1) {
          lines.push({
            y: (i - (n - 1) / 2) * ((radius * 2) / n),
            w: 4.5 + ((i * 7) % 3) * 4,
            delay: i * 0.045,
            color: i % 2 ? C.gray : C.amber,
          });
        }
        inst.shapes.push({ radius, lines });
      },
    };
  }

  function makeDraw() {
    return {
      rings(g, inst, t, fade, beatP, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        inst.shapes.forEach((s, i) => {
          const k = easeOutCubic(prog(t, s.delay));
          if (k <= 0) return;
          const r = k * s.rEnd * (1 + 0.04 * Math.sin(t * 1.4 + i)) + beatP * minD * 0.012;
          g.globalAlpha = (1 - k * 0.5) * fade;
          g.strokeStyle = s.color;
          g.lineWidth = s.w * (1 + beatP * 0.5);
          g.beginPath();
          g.arc(inst.cx, inst.cy, r, 0, 7);
          g.stroke();
        });
        const dk = easeOutBack(prog(t, 0));
        if (dk > 0) {
          g.globalAlpha = fade;
          g.fillStyle = C.amber;
          g.beginPath();
          g.arc(inst.cx, inst.cy, inst.dotR * dk * (1 + beatP * 0.2), 0, 7);
          g.fill();
        }
      },
      poly(g, inst, t, fade, beatP, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        inst.shapes.forEach((s, i) => {
          const k = easeOutCubic(prog(t, s.delay));
          if (k <= 0) return;
          const r = k * s.rEnd * (1 + beatP * 0.035 + 0.03 * Math.sin(t * 1.1 + i * 1.9));
          const rot = inst.rot0 + inst.dir * (1 - k) * 1.3 + t * 0.18 * inst.dir;
          g.globalAlpha = (1 - k * 0.3) * fade;
          g.strokeStyle = s.color;
          g.lineWidth = s.w * (1 + beatP * 0.4) + beatP * minD * 0.0015;
          tracePoly(g, inst.cx, inst.cy, r, s.sides, rot);
          g.stroke();
        });
      },
      spiral(g, inst, t, fade, beatP) {
        const rot = inst.rot0 + t * 0.45 * inst.dir + beatP * 0.05 * inst.dir;
        inst.shapes.forEach((s, i) => {
          const k = easeOutBack(prog(t, s.delay));
          if (k <= 0) return;
          const a = s.ang + rot;
          const r = s.rad * k * (1 + beatP * 0.04) + Math.sin(t * 1.5 + i * 0.5) * 4;
          g.globalAlpha = fade;
          drawPiece(
            g,
            i % 6 === 5 ? "square" : "circle",
            s.color,
            inst.cx + Math.cos(a) * r,
            inst.cy + Math.sin(a) * r,
            s.size * k * (1 + beatP * 0.25),
            a,
          );
        });
      },
      rays(g, inst, t, fade, beatP) {
        for (const s of inst.shapes) {
          const k = easeOutCubic(prog(t, s.delay, 0.5));
          if (k <= 0) continue;
          const rot = inst.rot0 + inst.dir * (1 - k) * 0.8 + t * 0.14 * inst.dir;
          const len = s.len * k * (1 + beatP * 0.09);
          const a = s.ang + rot;
          g.globalAlpha = 0.88 * fade;
          g.fillStyle = s.color;
          g.beginPath();
          g.moveTo(inst.cx, inst.cy);
          g.arc(inst.cx, inst.cy, inst.r0 + len, a - s.w, a + s.w);
          g.closePath();
          g.fill();
        }
      },
      confetti(g, inst, t, fade, beatP) {
        inst.shapes.forEach((s, i) => {
          const k = easeOutBack(prog(t, s.delay));
          if (k <= 0) return;
          const x = inst.cx + Math.cos(s.ang) * s.dist * k * (1 + beatP * 0.025);
          const y = inst.cy + Math.sin(s.ang) * s.dist * k * (1 + beatP * 0.025) + Math.sin(t * 2.2 + i * 1.3) * 6;
          g.globalAlpha = fade;
          drawPiece(g, s.kind, s.color, x, y, s.size * k * (1 + beatP * 0.18), s.spin * k + t * 0.6 * inst.dir);
        });
      },
      zigzag(g, inst, t, fade, beatP) {
        const s = inst.shapes[0];
        const k = easeOutCubic(prog(t, 0, 0.6));
        if (k <= 0) return;
        g.save();
        g.translate(0, Math.sin(t * 1.6) * 7);
        g.lineJoin = "round";
        g.lineCap = "round";
        g.save();
        g.translate(0, s.w * 2.1);
        g.globalAlpha = 0.4 * fade;
        g.strokeStyle = C.gray;
        g.lineWidth = s.w * (1 + beatP * 0.2);
        strokePartial(g, s.pts, s.lens, k * s.total);
        g.stroke();
        g.restore();
        g.globalAlpha = fade;
        g.strokeStyle = s.color;
        g.lineWidth = s.w * (1 + beatP * 0.3);
        const tip = strokePartial(g, s.pts, s.lens, k * s.total);
        g.stroke();
        g.fillStyle = C.gray;
        g.beginPath();
        g.arc(tip.x, tip.y, s.w * (1.1 + beatP * 0.45), 0, 7);
        g.fill();
        g.restore();
      },
      pop(g, inst, t, fade, beatP) {
        inst.shapes.forEach((s, i) => {
          const k = easeOutBack(prog(t, s.delay));
          if (k <= 0) return;
          g.globalAlpha = 0.96 * fade;
          drawPiece(
            g,
            s.kind,
            s.color,
            s.x,
            s.y + Math.sin(t * 2 + i * 1.7) * 7,
            s.size * k * (1 + beatP * 0.2),
            s.rot + t * 0.4 * inst.dir + beatP * 0.08 * inst.dir,
          );
        });
      },
      cross(g, inst, t, fade, beatP) {
        const s = inst.shapes[0];
        const k1 = easeOutBack(prog(t, 0));
        const k2 = easeOutBack(prog(t, 0.13));
        if (k1 <= 0) return;
        g.save();
        g.translate(inst.cx, inst.cy);
        g.rotate(inst.rot0 + inst.dir * (1 - k1) * 1.6 + Math.sin(t * 1.3) * 0.07 + beatP * 0.02 * inst.dir);
        const pulse = 1 + beatP * 0.12;
        g.scale(pulse, pulse);
        const L = s.size / 2;
        const w = s.w / 2;
        g.globalAlpha = fade;
        g.fillStyle = s.color;
        g.fillRect(-L * k1, -w, L * 2 * k1, w * 2);
        if (k2 > 0) g.fillRect(-w, -L * k2, w * 2, L * 2 * k2);
        g.globalAlpha = 0.6 * fade;
        g.strokeStyle = C.gray;
        g.lineWidth = Math.max(2, s.w * 0.28);
        g.beginPath();
        g.arc(0, 0, s.size * 0.68 * k1 * (1 + beatP * 0.08), 0, 7);
        g.stroke();
        g.restore();
      },
      orbit(g, inst, t, fade, beatP) {
        inst.shapes.forEach((s) => {
          const k = easeOutCubic(prog(t, s.delay));
          if (k <= 0) return;
          const a = s.ang0 + t * s.speed + inst.dir * (1 - k) * 1.8;
          const R = s.rad * k * (1 + beatP * 0.09);
          g.globalAlpha = fade;
          drawPiece(
            g,
            s.kind,
            s.color,
            inst.cx + Math.cos(a) * R,
            inst.cy + Math.sin(a) * R,
            s.size * (0.6 + 0.4 * k) * (1 + beatP * 0.15),
            t * 1.2 * inst.dir,
          );
        });
        const ck = easeOutBack(prog(t, 0));
        if (ck > 0) {
          g.globalAlpha = fade;
          drawPiece(g, "circle", C.amber, inst.cx, inst.cy, inst.coreR * ck * (1 + beatP * 0.2), 0);
        }
      },
      wave(g, inst, t, fade, beatP, fxW) {
        const step = Math.max(14, fxW / 28);
        for (const s of inst.shapes) {
          const k = easeOutCubic(prog(t, s.delay, 0.6));
          if (k <= 0) continue;
          const off = (1 - k) * (fxW + 120) * s.side;
          const amp = s.amp * (0.6 + 0.4 * k) * (1 + beatP * 0.3);
          g.globalAlpha = 0.9 * fade;
          g.fillStyle = s.color;
          g.beginPath();
          for (let x = -60; x <= fxW + 60; x += step) {
            const y = s.y0 + Math.sin((x / s.wl) * Math.PI * 2 + t * s.speed) * amp;
            x === -60 ? g.moveTo(x + off, y) : g.lineTo(x + off, y);
          }
          for (let x = fxW + 60; x >= -60; x -= step) {
            const y = s.y0 + s.th * (1 + beatP * 0.12) + Math.sin((x / s.wl) * Math.PI * 2 + t * s.speed + 0.9) * amp;
            g.lineTo(x + off, y);
          }
          g.closePath();
          g.fill();
        }
      },
      stars(g, inst, t, fade, beatP) {
        inst.shapes.forEach((s, i) => {
          const k = easeOutElastic(prog(t, s.delay));
          if (k <= 0) return;
          const tw = 1 + 0.15 * Math.sin(t * 3.2 + i * 2.1) + beatP * 0.18;
          g.globalAlpha = 0.97 * fade;
          drawPiece(g, "star", s.color, s.x, s.y, s.r * k * tw, s.rot + t * 0.7 * inst.dir);
        });
      },
      grid(g, inst, t, fade, beatP) {
        const s = inst.shapes[0];
        const R = s.radius * (1 + beatP * 0.06 + 0.03 * Math.sin(t * 1.3));
        g.save();
        g.translate(inst.cx, inst.cy);
        g.rotate(inst.rot0 + t * 0.22 * inst.dir + beatP * 0.025 * inst.dir);
        g.beginPath();
        g.arc(0, 0, R, 0, 7);
        g.clip();
        for (const ln of s.lines) {
          const k = easeOutCubic(prog(t, ln.delay));
          if (k <= 0) continue;
          g.globalAlpha = 0.92 * fade;
          g.strokeStyle = ln.color;
          g.lineWidth = ln.w * (1 + beatP * 0.35);
          g.beginPath();
          g.moveTo(-R * k, ln.y);
          g.lineTo(R * k, ln.y);
          g.stroke();
        }
        g.restore();
        const ok = easeOutBack(prog(t, 0));
        if (ok > 0) {
          g.globalAlpha = fade;
          g.strokeStyle = C.amber;
          g.lineWidth = 6 * (1 + beatP * 0.35);
          g.beginPath();
          g.arc(inst.cx, inst.cy, R * ok, 0, 7);
          g.stroke();
        }
      },
    };
  }

  const BUILD = makeBuild();
  const DRAW = makeDraw();

  function reduceMotion() {
    return !!(global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function create(canvas) {
    const g = canvas.getContext("2d");
    const list = [];
    let fxW = 1;
    let fxH = 1;
    let cursor = 0;
    let beatP = 0;
    const cx0 = () => fxW / 2;
    const cy0 = () => fxH / 2;

    function resize() {
      const dpr = Math.min(global.devicePixelRatio || 1, 2);
      const box = canvas.getBoundingClientRect();
      fxW = Math.max(1, box.width || canvas.clientWidth || 1);
      fxH = Math.max(1, box.height || canvas.clientHeight || 1);
      const w = Math.round(fxW * dpr);
      const h = Math.round(fxH * dpr);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      for (const item of list) {
        item.cx = cx0();
        item.cy = cy0();
      }
    }

    function spawn(type) {
      if (reduceMotion()) return null;
      const name = type && BUILD[type] ? type : EFFECTS[cursor % EFFECTS.length];
      cursor += 1;
      const now = performance.now() / 1000;
      for (const item of list) {
        if (item.state !== "out") {
          item.state = "out";
          item.outT0 = now;
        }
      }
      while (list.length > MAX_LAYERS) list.shift();
      const rng = mulberry32((Math.random() * 1e9) | 0);
      const inst = {
        type: name,
        cx: cx0(),
        cy: cy0(),
        t0: now,
        state: "in",
        outT0: 0,
        rot0: rng() * Math.PI * 2,
        dir: rng() < 0.5 ? -1 : 1,
        shapes: [],
      };
      BUILD[name](inst, rng, fxW, fxH);
      list.push(inst);
      return name;
    }

    function draw(opts) {
      resize();
      beatP = opts && opts.beat != null ? clamp01(opts.beat) : beatP;
      const now = (opts && opts.now) || performance.now() / 1000;
      g.clearRect(0, 0, fxW, fxH);
      g.save();
      g.globalAlpha = 0.48;
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const inst = list[i];
        let outK = 0;
        if (inst.state === "out") {
          outK = clamp01((now - inst.outT0) / FX_OUT);
          if (outK >= 1) {
            list.splice(i, 1);
            continue;
          }
        }
        const t = now - inst.t0;
        if (t < 0) continue;
        const fade = 1 - smooth(outK);
        const sc = inst.state === "out" ? 1 - 0.22 * outK : 1 + beatP * 0.02;
        g.save();
        g.translate(inst.cx, inst.cy);
        g.scale(sc, sc);
        g.translate(-inst.cx, -inst.cy);
        DRAW[inst.type](g, inst, t, fade, beatP, fxW, fxH);
        g.restore();
      }
      g.restore();
    }

    function clear() {
      list.length = 0;
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.clearRect(0, 0, canvas.width, canvas.height);
    }

    resize();
    global.addEventListener("resize", resize);
    return { spawn, draw, clear, resize, setBeat: (p) => { beatP = clamp01(p); } };
  }

  let party = null;

  function bindParty(canvas) {
    if (!global.confetti || !canvas) return null;
    party = global.confetti.create(canvas, {
      resize: true,
      useWorker: false,
      disableForReducedMotion: true,
    });
    return party;
  }

  function celebrate(kind) {
    if (reduceMotion()) return;
    const fire = party || global.confetti;
    if (!fire) return;
    const colors = ["#f5c16c", "#ff4d8d", "#ffffff", "#6ec8ff"];
    if (kind === "side") {
      fire({ particleCount: 55, angle: 60, spread: 62, origin: { x: 0, y: 0.7 }, colors });
      fire({ particleCount: 55, angle: 120, spread: 62, origin: { x: 1, y: 0.7 }, colors });
      return;
    }
    fire({ particleCount: 90, spread: 78, startVelocity: 42, origin: { y: 0.62 }, colors });
  }

  function hookTexts(cues) {
    const counts = {};
    for (const cue of cues || []) {
      const text = String(cue.text || "").trim();
      if (!text) continue;
      counts[text] = (counts[text] || 0) + 1;
    }
    return new Set(Object.keys(counts).filter((text) => counts[text] >= 3));
  }

  global.LovStageFx = { EFFECTS, create, bindParty, celebrate, hookTexts, reduceMotion };
})(window);
