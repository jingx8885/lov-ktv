(function (global) {
  "use strict";

  const EFFECTS = [
    "rings",
    "poly",
    "spiral",
    "rays",
    "confetti",
    "zigzag",
    "pop",
    "cross",
    "orbit",
    "wave",
    "stars",
    "grid"
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

  global.LovStageFxPrimitives = {
    EFFECTS,
    C,
    ACCENTS,
    FX_IN,
    FX_OUT,
    MAX_LAYERS,
    mulberry32,
    clamp01,
    smooth,
    easeOutCubic,
    easeOutBack,
    easeOutElastic,
    prog,
    pickColor,
    tracePoly,
    traceStar,
    drawPiece,
    strokePartial
  };
})(window);
