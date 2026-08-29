(function (global) {
  "use strict";
  const { C, ACCENTS, pickColor } = global.LovStageFxPrimitives;

  function makeBuild() {
    return {
      rings(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        for (let i = 0; i < 7; i += 1) {
          inst.shapes.push({
            delay: i * 0.05,
            rEnd: minD * (0.13 + rng() * 0.29),
            w: 5 + rng() * 9,
            color: pickColor(rng)
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
          [0.17, C.amber, 0.18]
        ].forEach(([s, color, d], i) => {
          inst.shapes.push({
            sides,
            delay: d,
            color,
            rEnd: minD * Number(s),
            w: minD * (0.034 - i * 0.007)
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
            color: pickColor(rng)
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
            color: rng() < 0.12 ? ACCENTS[(rng() * 3) | 0] : i % 2 ? C.gray : C.amber
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
            color: pickColor(rng)
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
              y: fxH * (i % 2 ? 0.72 + rng() * 0.14 : 0.14 + rng() * 0.14)
            });
          } else {
            pts.push({
              x: fxW * (i % 2 ? 0.7 + rng() * 0.16 : 0.14 + rng() * 0.16),
              y: -fxH * 0.08 + f * fxH * 1.16
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
            color: pickColor(rng)
          });
        }
      },
      cross(inst, rng, fxW, fxH) {
        const minD = Math.min(fxW, fxH);
        const size = minD * (0.6 + rng() * 0.25);
        inst.shapes.push({
          size,
          w: size * (0.14 + rng() * 0.08),
          color: rng() < 0.2 ? ACCENTS[(rng() * 3) | 0] : C.amber
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
            color: pickColor(rng)
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
            color: rng() < 0.12 ? ACCENTS[(rng() * 3) | 0] : i % 2 ? C.gray : C.amber
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
            color: pickColor(rng)
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
            color: i % 2 ? C.gray : C.amber
          });
        }
        inst.shapes.push({ radius, lines });
      }
    };
  }

  global.LovStageFxBuild = makeBuild();
})(window);
