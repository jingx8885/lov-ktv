(function (global) {
  const overviewCache = new Map();

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function liveLevel(freq, wave) {
    let peak = 0;
    if (wave && wave.length) {
      let sum = 0;
      const step = Math.max(1, Math.floor(wave.length / 160));
      for (let i = 0; i < wave.length; i += step) {
        const v = (wave[i] - 128) / 128;
        sum += v * v;
        peak = Math.max(peak, Math.abs(v));
      }
      const rms = Math.sqrt(sum / Math.max(1, Math.floor(wave.length / step)));
      if (rms > 0.01 || peak > 0.02) return clamp(rms * 0.7 + peak * 0.5, 0, 1);
    }
    if (freq && freq.length) {
      let sum = 0;
      const n = Math.min(48, freq.length);
      for (let i = 2; i < n; i += 1) sum += freq[i];
      return clamp((sum / Math.max(1, n - 2)) / 255, 0, 1);
    }
    return 0;
  }

  function decodeOverview(url) {
    if (overviewCache.has(url)) return overviewCache.get(url);
    const pending = (async () => {
      const res = await fetch(url);
      if (!res.ok) throw new Error("waveform " + res.status);
      const buf = await res.arrayBuffer();
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = new Ctx();
      const audio = await ctx.decodeAudioData(buf.slice(0));
      const left = audio.getChannelData(0);
      const right = audio.numberOfChannels > 1 ? audio.getChannelData(1) : null;
      const buckets = 720;
      const peaks = new Float32Array(buckets);
      const block = Math.max(1, Math.floor(left.length / buckets));
      for (let i = 0; i < buckets; i += 1) {
        const start = i * block;
        const end = Math.min(left.length, start + block);
        const stride = Math.max(1, Math.floor((end - start) / 160));
        let energy = 0;
        let n = 0;
        for (let j = start; j < end; j += stride) {
          const l = left[j];
          const r = right ? right[j] : l;
          energy += l * l + r * r;
          n += 2;
        }
        peaks[i] = Math.sqrt(energy / Math.max(1, n));
      }
      const ranked = Array.from(peaks).sort((a, b) => a - b);
      const lo = ranked[Math.floor(ranked.length * 0.06)] || 0;
      const hi = ranked[Math.floor(ranked.length * 0.94)] || 1;
      const span = Math.max(hi * 0.2, hi - lo, 1e-5);
      for (let i = 0; i < buckets; i += 1) {
        peaks[i] = clamp((peaks[i] - lo) / span, 0, 1.15);
      }
      ctx.close();
      return peaks;
    })();
    overviewCache.set(url, pending);
    pending.then((peaks) => overviewCache.set(url, peaks)).catch(() => overviewCache.delete(url));
    return pending;
  }

  function getOverview(url) {
    const hit = overviewCache.get(url);
    if (!hit || typeof hit.then === "function") return null;
    return hit;
  }

  function sampleOverview(overview, t0, t1) {
    if (!overview || !overview.length) return 0;
    const a = Math.max(0, Math.floor(t0 * overview.length));
    const b = Math.min(overview.length, Math.max(a + 1, Math.ceil(t1 * overview.length)));
    let m = 0;
    for (let i = a; i < b; i += 1) if (overview[i] > m) m = overview[i];
    return m;
  }

  function create(canvas) {
    let sourceUrl = "";
    let overview = null;
    let loadId = 0;

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const box = canvas.getBoundingClientRect();
      const w = Math.max(1, Math.round(box.width * dpr));
      const h = Math.max(1, Math.round(box.height * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      return dpr;
    }

    function setSource(url) {
      if (!url || url === sourceUrl) return;
      sourceUrl = url;
      overview = null;
      const id = (loadId += 1);
      decodeOverview(url).then((peaks) => {
        if (id === loadId) overview = peaks;
      }).catch(() => {});
    }

    function roundBar(ctx, x, y, bw, bh, r) {
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, bw, bh, r);
      else ctx.rect(x, y, bw, bh);
    }

    function draw(opts) {
      const dpr = resize();
      const ctx = canvas.getContext("2d");
      const w = canvas.width;
      const h = canvas.height;
      const playing = !!opts.playing;
      const playMs = opts.playMs || 0;
      const duration = opts.duration || 0;
      const cues = opts.cues || [];
      const selected = opts.selected == null ? -1 : opts.selected;
      const live = playing ? liveLevel(opts.freq, opts.wave) : 0;
      const railH = Math.max(18 * dpr, Math.min(h * 0.2, 36 * dpr));
      const floor = h - railH;
      const mid = floor * 0.52;
      const ampH = floor * 0.38;
      const bars = clamp(Math.round(w / (dpr * 5.1)), 64, 168);
      const playX = duration > 0 ? (playMs / duration) * w : 0;
      const slot = w / bars;
      const barW = Math.max(1.6 * dpr, slot * 0.58);
      const pulse = 0.55 + 0.45 * Math.sin((playMs / 180) + live * 4);

      ctx.clearRect(0, 0, w, h);
      const night = ctx.createLinearGradient(0, 0, 0, h);
      night.addColorStop(0, "#10182c");
      night.addColorStop(0.55, "#070b16");
      night.addColorStop(1, "#04060d");
      ctx.fillStyle = night;
      ctx.fillRect(0, 0, w, h);

      const wash = ctx.createRadialGradient(playX || w * 0.42, mid, 8 * dpr, playX || w * 0.42, mid, h * 0.95);
      wash.addColorStop(0, `rgba(255,77,141,${0.16 + live * 0.28})`);
      wash.addColorStop(0.45, `rgba(80,40,140,${0.1 + live * 0.08})`);
      wash.addColorStop(1, "rgba(4,6,14,0)");
      ctx.fillStyle = wash;
      ctx.fillRect(0, 0, w, h);

      ctx.save();
      ctx.globalAlpha = 0.12;
      ctx.strokeStyle = "#6d7aa8";
      ctx.lineWidth = dpr;
      for (let y = Math.round(floor * 0.18); y < floor; y += Math.round(10 * dpr)) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      ctx.restore();

      if (playX > 0) {
        const played = ctx.createLinearGradient(0, 0, playX, 0);
        played.addColorStop(0, "rgba(255,77,141,0.04)");
        played.addColorStop(1, "rgba(255,193,108,0.16)");
        ctx.fillStyle = played;
        ctx.fillRect(0, 0, playX, floor);
      }

      ctx.save();
      ctx.strokeStyle = "rgba(255,77,141,0.28)";
      ctx.lineWidth = 1.2 * dpr;
      ctx.shadowColor = "rgba(255,77,141,0.45)";
      ctx.shadowBlur = 10 * dpr;
      ctx.beginPath();
      ctx.moveTo(0, mid);
      ctx.lineTo(w, mid);
      ctx.stroke();
      ctx.restore();

      for (let i = 0; i < bars; i += 1) {
        const t0 = i / bars;
        const t1 = (i + 1) / bars;
        let level = overview
          ? sampleOverview(overview, t0, t1)
          : 0.16 + 0.22 * Math.abs(Math.sin(t0 * 17.2)) + 0.1 * Math.abs(Math.sin(t0 * 41 + playMs * 0.0015));
        level = 0.06 + Math.pow(clamp(level, 0, 1), 0.72) * 0.94;
        const center = (i + 0.5) * slot;
        const near = playX > 0 && Math.abs(center - playX) < slot * 3.4;
        if (playing && near) level = clamp(level * (1.08 + live * 0.7), 0.12, 1);
        const up = level * ampH * (near ? 1.08 + live * 0.18 : 1);
        const down = up * 0.72;
        const playedBar = center <= playX;
        const x = center - barW / 2;
        const glow = ctx.createLinearGradient(0, mid - up, 0, mid + down);
        if (playedBar) {
          glow.addColorStop(0, "rgba(255,236,196,0.55)");
          glow.addColorStop(0.4, "rgba(255,77,141,0.38)");
          glow.addColorStop(1, "rgba(255,77,141,0)");
        } else {
          glow.addColorStop(0, "rgba(120,210,255,0.2)");
          glow.addColorStop(1, "rgba(80,90,130,0)");
        }
        ctx.fillStyle = glow;
        roundBar(ctx, x - dpr, mid - up - 2 * dpr, barW + 2 * dpr, up + down + 4 * dpr, barW);
        ctx.fill();

        const core = ctx.createLinearGradient(0, mid - up, 0, mid + down);
        if (playedBar) {
          core.addColorStop(0, "rgba(255,244,214,0.98)");
          core.addColorStop(0.28, "rgba(255,168,80,0.98)");
          core.addColorStop(0.58, "rgba(255,77,141,0.96)");
          core.addColorStop(1, "rgba(120,20,70,0.18)");
        } else {
          core.addColorStop(0, "rgba(186,220,255,0.42)");
          core.addColorStop(0.5, "rgba(92,118,168,0.34)");
          core.addColorStop(1, "rgba(40,50,80,0.08)");
        }
        ctx.fillStyle = core;
        roundBar(ctx, x, mid - up, barW, up + down, Math.max(1, barW / 2));
        ctx.fill();
      }

      const glass = ctx.createLinearGradient(0, 0, 0, floor * 0.38);
      glass.addColorStop(0, "rgba(255,255,255,0.08)");
      glass.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = glass;
      ctx.fillRect(0, 0, w, floor * 0.38);

      ctx.fillStyle = "rgba(6,8,16,0.88)";
      ctx.fillRect(0, floor, w, railH);
      const railLine = ctx.createLinearGradient(0, 0, w, 0);
      railLine.addColorStop(0, "rgba(255,77,141,0)");
      railLine.addColorStop(0.5, "rgba(255,77,141,0.55)");
      railLine.addColorStop(1, "rgba(245,193,108,0)");
      ctx.fillStyle = railLine;
      ctx.fillRect(0, floor, w, Math.max(1, 1.2 * dpr));

      if (duration > 0 && cues.length) {
        const padY = 5 * dpr;
        const pillH = Math.max(7 * dpr, railH - padY * 2);
        cues.forEach((cue, index) => {
          const x0 = (Number(cue.start_ms || 0) / duration) * w;
          const x1 = (Number(cue.end_ms || cue.start_ms || 0) / duration) * w;
          const on = index === selected;
          const past = playMs >= Number(cue.end_ms || 0);
          const width = Math.max(3 * dpr, x1 - x0 - dpr);
          ctx.fillStyle = on
            ? "rgba(255,77,141,0.92)"
            : past
              ? "rgba(255,77,141,0.28)"
              : "rgba(150,168,210,0.22)";
          if (on) {
            ctx.shadowColor = "rgba(255,77,141,0.7)";
            ctx.shadowBlur = 10 * dpr;
          }
          roundBar(ctx, x0, floor + padY, width, pillH, pillH / 2);
          ctx.fill();
          ctx.shadowBlur = 0;
          if (on) {
            ctx.fillStyle = "rgba(255,236,196,0.95)";
            const fillW = clamp(((playMs - cue.start_ms) / Math.max(1, cue.end_ms - cue.start_ms)) * width, 0, width);
            roundBar(ctx, x0, floor + padY, fillW, pillH, pillH / 2);
            ctx.fill();
          }
        });
      }

      if (duration > 0) {
        ctx.save();
        ctx.shadowColor = "#ff4d8d";
        ctx.shadowBlur = (18 + live * 16) * dpr;
        const beam = ctx.createLinearGradient(playX, 0, playX, h);
        beam.addColorStop(0, "rgba(255,236,196,0.95)");
        beam.addColorStop(0.45, "rgba(255,77,141,0.95)");
        beam.addColorStop(1, "rgba(255,77,141,0.15)");
        ctx.strokeStyle = beam;
        ctx.lineWidth = 2.4 * dpr;
        ctx.beginPath();
        ctx.moveTo(playX, 6 * dpr);
        ctx.lineTo(playX, h - 4 * dpr);
        ctx.stroke();
        ctx.restore();

        const cap = 5.2 * dpr * (playing ? 0.92 + pulse * 0.18 : 1);
        ctx.fillStyle = "#ffe8bc";
        ctx.beginPath();
        ctx.moveTo(playX, 4 * dpr);
        ctx.lineTo(playX + cap, 12 * dpr);
        ctx.lineTo(playX - cap, 12 * dpr);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "#ff4d8d";
        ctx.beginPath();
        ctx.arc(playX, floor, 3.6 * dpr, 0, Math.PI * 2);
        ctx.fill();
        if (playing) {
          ctx.strokeStyle = `rgba(255,77,141,${0.28 + live * 0.35})`;
          ctx.lineWidth = 1.4 * dpr;
          ctx.beginPath();
          ctx.arc(playX, floor, (7 + pulse * 5) * dpr, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    }

    return { draw, resize, setSource };
  }

  function hookAnalyser(audio, prev, opts) {
    if (prev && prev.audio === audio && prev.analyser) {
      if (prev.ctx && prev.ctx.state === "suspended") prev.ctx.resume().catch(() => {});
      return prev;
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx || !audio) return prev || null;
    if (!audio.crossOrigin) audio.crossOrigin = "anonymous";
    const ctx = (opts && opts.ctx) || new Ctx({ latencyHint: (opts && opts.latencyHint) || "interactive" });
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.55;
    analyser.minDecibels = -90;
    analyser.maxDecibels = -20;
    let source = null;
    try {
      source = ctx.createMediaElementSource(audio);
    } catch (err) {
      return prev || { audio, ctx, analyser, freq: new Uint8Array(analyser.frequencyBinCount), time: new Uint8Array(analyser.fftSize) };
    }
    const gain = ctx.createGain();
    gain.gain.value = 1;
    source.connect(gain);
    gain.connect(ctx.destination);
    const splitter = ctx.createChannelSplitter(2);
    source.connect(splitter);
    splitter.connect(analyser, 0);
    ctx.resume().catch(() => {});
    return {
      audio,
      ctx,
      source,
      gain,
      analyser,
      freq: new Uint8Array(analyser.frequencyBinCount),
      time: new Uint8Array(analyser.fftSize),
    };
  }

  function pull(hooked) {
    if (!hooked || !hooked.analyser) return null;
    hooked.analyser.getByteFrequencyData(hooked.freq);
    if (hooked.time) hooked.analyser.getByteTimeDomainData(hooked.time);
    return hooked.freq;
  }

  global.LovBands = { create, hookAnalyser, pull, getOverview, decodeOverview };
})(window);
