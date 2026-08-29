(function (global) {
  "use strict";
  const { EFFECTS, FX_IN, FX_OUT, MAX_LAYERS, mulberry32, clamp01, smooth } = global.LovStageFxPrimitives;
  const BUILD = global.LovStageFxBuild;
  const DRAW = global.LovStageFxDraw;

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
      // Keep the layer cap strict before adding the new instance.
      while (list.length >= MAX_LAYERS) list.shift();
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
      const now = opts && opts.now != null ? opts.now : performance.now() / 1000;
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


  global.LovStageFxRuntime = { create, reduceMotion };
})(window);
