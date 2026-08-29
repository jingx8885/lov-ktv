(function (global) {
  "use strict";
  const { C, easeOutCubic, easeOutBack, easeOutElastic, prog, tracePoly, drawPiece, strokePartial } =
    global.LovStageFxPrimitives;

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
            a
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
            s.rot + t * 0.4 * inst.dir + beatP * 0.08 * inst.dir
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
            t * 1.2 * inst.dir
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
      }
    };
  }

  global.LovStageFxDraw = makeDraw();
})(window);
