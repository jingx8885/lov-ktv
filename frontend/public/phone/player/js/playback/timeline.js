(function (global) {
  const MIN_MS = 200;
  const SNAP_NEAR = 280;
  const SNAP_MS = 160;

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function fitTokens(cue, start, end) {
    const tokens = cue.tokens || [];
    if (!tokens.length) {
      cue.start_ms = start;
      cue.end_ms = end;
      return;
    }
    const oldStart = Number(tokens[0].start_ms ?? cue.start_ms);
    const oldEnd = Number(tokens[tokens.length - 1].end_ms ?? cue.end_ms);
    const oldSpan = Math.max(1, oldEnd - oldStart);
    const span = Math.max(MIN_MS, end - start);
    tokens.forEach((tok) => {
      const relS = (Number(tok.start_ms) - oldStart) / oldSpan;
      const relE = (Number(tok.end_ms) - oldStart) / oldSpan;
      tok.start_ms = start + Math.round(span * relS);
      tok.end_ms = Math.max(tok.start_ms + 40, start + Math.round(span * relE));
    });
    tokens[0].start_ms = start;
    tokens[tokens.length - 1].end_ms = end;
    cue.start_ms = start;
    cue.end_ms = end;
  }

  function shiftCue(cue, delta) {
    fitTokens(cue, cue.start_ms + delta, cue.end_ms + delta);
  }

  function repair(cues, duration) {
    const limit = duration > 0 ? duration : 1e12;
    for (let i = 0; i < cues.length; i += 1) {
      const prevEnd = i ? cues[i - 1].end_ms : 0;
      const nxt = i + 1 < cues.length ? cues[i + 1].start_ms : limit;
      let start = Math.max(0, prevEnd, cues[i].start_ms);
      let end = Math.max(start + MIN_MS, cues[i].end_ms);
      if (end > nxt) {
        end = nxt;
        if (end < start + MIN_MS) {
          start = Math.max(prevEnd, nxt - MIN_MS);
          end = nxt;
        }
      }
      fitTokens(cues[i], start, end);
    }
  }

  function create(opts) {
    const root = opts.root;
    const stage = opts.stage;
    const wave = opts.wave;
    const voice = opts.voice || null;
    const ruler = opts.ruler;
    const track = opts.track;
    const surface = root.querySelector(".tl-viewport") || root;
    let pxPerSec = 40;
    let duration = 0;
    let playMs = 0;
    let chain = false;
    let dragging = null;
    let waveUrl = "";
    let voiceUrl = "";
    let voiceOn = true;
    let mixOn = true;
    let lastZoom = 0;
    let lastDur = 0;

    function cues() {
      return opts.getCues() || [];
    }

    function audio() {
      return opts.getAudio();
    }

    function xOf(ms) {
      return (ms / 1000) * pxPerSec;
    }

    function msOf(x) {
      return (x / pxPerSec) * 1000;
    }

    function pad() {
      return surface.clientWidth / 2;
    }

    function contentWidth() {
      return Math.max(xOf(duration || 1000), 80);
    }

    function applyOffset() {
      stage.style.transform = `translateX(${pad() - xOf(playMs)}px)`;
    }

    function seek(ms) {
      const a = audio();
      const max = (a && a.duration ? a.duration * 1000 : duration) || 0;
      const next = clamp(ms, 0, Math.max(0, max));
      playMs = next;
      if (a && a.duration) {
        try {
          a.currentTime = next / 1000;
        } catch (err) {}
      }
      applyOffset();
      if (opts.onSeek) opts.onSeek(next);
    }

    function peekOverview(url) {
      if (!url || !global.LovBands) return null;
      const hit = LovBands.getOverview(url);
      if (hit) return hit;
      const pending = LovBands.decodeOverview(url);
      if (pending && pending.then) pending.then(() => drawWave()).catch(() => {});
      return null;
    }

    function paintLane(canvas, overview, fill) {
      if (!canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(1, Math.round(contentWidth() * dpr));
      const h = Math.max(1, Math.round(44 * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      canvas.style.width = contentWidth() + "px";
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#0a0e18";
      ctx.fillRect(0, 0, w, h);
      const mid = h * 0.5;
      const bars = Math.max(80, Math.round(w / (2.2 * dpr)));
      const slot = w / bars;
      const barW = Math.max(dpr, slot * 0.7);
      for (let i = 0; i < bars; i += 1) {
        const t0 = i / bars;
        const t1 = (i + 1) / bars;
        let level = 0.06;
        if (overview && overview.length) {
          const a0 = Math.floor(t0 * overview.length);
          const b0 = Math.min(overview.length, Math.max(a0 + 1, Math.ceil(t1 * overview.length)));
          let m = 0;
          for (let k = a0; k < b0; k += 1) if (overview[k] > m) m = overview[k];
          level = 0.06 + Math.pow(m, 0.78) * 0.94;
        }
        const up = level * mid * 0.92;
        ctx.fillStyle = fill;
        ctx.fillRect((i + 0.5) * slot - barW / 2, mid - up, barW, up * 2);
      }
    }

    function drawWave() {
      const a = audio();
      const url = a && (a.currentSrc || a.src);
      paintLane(wave, peekOverview(url), mixOn ? "rgba(255,77,141,0.78)" : "rgba(255,77,141,0.18)");
      if (voice)
        paintLane(voice, peekOverview(voiceUrl), voiceOn ? "rgba(245,193,108,0.88)" : "rgba(245,193,108,0.18)");
      waveUrl = url || "";
      lastZoom = pxPerSec;
      lastDur = duration;
    }

    function renderRuler() {
      const step = pxPerSec >= 140 ? 1 : pxPerSec >= 80 ? 2 : 5;
      const marks = [];
      const end = Math.max(duration, 1000);
      for (let s = 0; s <= end / 1000 + 0.01; s += step) {
        const m = Math.floor(s / 60);
        const sec = Math.floor(s % 60);
        marks.push(`<i style="left:${xOf(s * 1000)}px"><b></b><em>${m}:${String(sec).padStart(2, "0")}</em></i>`);
      }
      ruler.style.width = contentWidth() + "px";
      ruler.innerHTML = marks.join("");
    }

    function renderClips() {
      const list = cues();
      const selected = opts.selected ? opts.selected() : -1;
      track.style.width = contentWidth() + "px";
      track.innerHTML = list
        .map((cue, index) => {
          const w = Math.max(8, xOf(cue.end_ms - cue.start_ms));
          const on = index === selected ? " on" : "";
          const now = playMs >= cue.start_ms && playMs < cue.end_ms ? " now" : "";
          return (
            `<div class="tl-clip${on}${now}" data-cue="${index}" style="left:${xOf(cue.start_ms)}px;width:${w}px">` +
            `<span class="tl-handle tl-l" data-edge="start"></span>` +
            `<span class="tl-clip-text">${escape(cue.text)}</span>` +
            `<span class="tl-handle tl-r" data-edge="end"></span></div>`
          );
        })
        .join("");
    }

    function escape(text) {
      return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function layoutChrome() {
      const width = contentWidth();
      wave.style.width = width + "px";
      if (voice) voice.style.width = width + "px";
      ruler.style.width = width + "px";
      track.style.width = width + "px";
      applyOffset();
    }

    function render() {
      const a = audio();
      duration = a && a.duration ? a.duration * 1000 : duration;
      layoutChrome();
      renderRuler();
      renderClips();
      if (
        pxPerSec !== lastZoom ||
        (a && (a.currentSrc || a.src) !== waveUrl) ||
        Math.abs(duration - lastDur) > 250 ||
        !wave.width
      ) {
        drawWave();
      }
    }

    function highlight() {
      const selected = opts.selected ? opts.selected() : -1;
      track.querySelectorAll(".tl-clip").forEach((el) => {
        const index = Number(el.getAttribute("data-cue"));
        const cue = cues()[index];
        el.classList.toggle("on", index === selected);
        el.classList.toggle("now", !!(cue && playMs >= cue.start_ms && playMs < cue.end_ms));
      });
    }

    function snap(ms, ignore) {
      const list = cues();
      let best = ms;
      let dist = 1e9;
      const consider = (edge, window) => {
        const d = Math.abs(edge - ms);
        if (d <= window && d < dist) {
          dist = d;
          best = edge;
        }
      };
      consider(playMs, SNAP_NEAR);
      if (ignore > 0) consider(list[ignore - 1].end_ms, SNAP_NEAR);
      if (ignore >= 0 && ignore + 1 < list.length) consider(list[ignore + 1].start_ms, SNAP_NEAR);
      list.forEach((cue, index) => {
        if (index === ignore) return;
        consider(cue.start_ms, SNAP_MS);
        consider(cue.end_ms, SNAP_MS);
      });
      return best;
    }

    function onChange() {
      if (opts.onChange) opts.onChange();
      renderClips();
    }

    function hitTest(target) {
      const clip = target.closest(".tl-clip");
      if (!clip) return null;
      const index = Number(clip.getAttribute("data-cue"));
      const handle = target.closest("[data-edge]");
      return { index, edge: handle ? handle.getAttribute("data-edge") : "move", clip };
    }

    function axisX(event) {
      return root.dataset.axis === "y" ? event.clientY : event.clientX;
    }

    function pointerDown(event) {
      if (event.button && event.button !== 0) return;
      const hit = hitTest(event.target);
      const startX = axisX(event);
      if (hit) {
        if (opts.onSelect) opts.onSelect(hit.index);
        highlight();
        const cue = cues()[hit.index];
        dragging = {
          kind: hit.edge,
          index: hit.index,
          startX,
          startMs: cue.start_ms,
          endMs: cue.end_ms,
          moved: false
        };
        if (opts.onGrab) opts.onGrab();
      } else {
        dragging = {
          kind: "scrub",
          startX,
          playMs,
          moved: false
        };
      }
      surface.setPointerCapture(event.pointerId);
      event.preventDefault();
    }

    function pointerMove(event) {
      if (!dragging) return;
      const dx = axisX(event) - dragging.startX;
      if (Math.abs(dx) > 4) dragging.moved = true;
      const delta = msOf(dx);
      const list = cues();
      if (dragging.kind === "scrub") {
        seek(dragging.playMs - delta);
        return;
      }
      const i = dragging.index;
      const cue = list[i];
      if (!cue) return;
      if (dragging.kind === "move") {
        const last = chain ? list.length : i + 1;
        const raw = snap(dragging.startMs + delta, i);
        const shift = raw - cue.start_ms;
        for (let n = i; n < last; n += 1) shiftCue(list[n], shift);
        repair(list, duration);
      } else if (dragging.kind === "start") {
        const prevEnd = i ? list[i - 1].end_ms : 0;
        let start = snap(dragging.startMs + delta, i);
        start = clamp(start, prevEnd, cue.end_ms - MIN_MS);
        fitTokens(cue, start, cue.end_ms);
      } else if (dragging.kind === "end") {
        const nxt = i + 1 < list.length ? list[i + 1].start_ms : duration || 1e12;
        let end = snap(dragging.endMs + delta, i);
        end = clamp(end, cue.start_ms + MIN_MS, nxt);
        fitTokens(cue, cue.start_ms, end);
      }
      if (opts.onChange) opts.onChange();
      renderClips();
    }

    function pointerUp() {
      if (dragging && dragging.kind !== "scrub") {
        const cue = cues()[dragging.index];
        if (dragging.moved && opts.onChange) opts.onChange();
        if (cue) {
          seek(cue.start_ms);
          if (opts.onReleaseCue) opts.onReleaseCue(cue);
        }
      }
      dragging = null;
    }

    surface.addEventListener("pointerdown", pointerDown);
    surface.addEventListener("pointermove", pointerMove);
    surface.addEventListener("pointerup", pointerUp);
    surface.addEventListener("pointercancel", pointerUp);

    function sync(ms, dur) {
      if (dur) duration = dur;
      if (!dragging || dragging.kind === "scrub") playMs = ms;
      if (dragging && dragging.kind === "scrub") return;
      applyOffset();
      highlight();
      const a = audio();
      const url = a && (a.currentSrc || a.src);
      if (
        (url && url !== waveUrl && global.LovBands && LovBands.getOverview(url)) ||
        Math.abs(duration - lastDur) > 250
      )
        drawWave();
    }

    function zoom(dir) {
      pxPerSec = clamp(pxPerSec * (dir > 0 ? 1.35 : 1 / 1.35), 36, 220);
      render();
    }

    function setChain(on) {
      chain = !!on;
    }

    function setVoiceUrl(url) {
      voiceUrl = url || "";
      lastZoom = 0;
      drawWave();
    }

    function setVoiceOn(on) {
      voiceOn = !!on;
      root.classList.toggle("voice-off", !voiceOn);
      lastZoom = 0;
      drawWave();
    }

    function setMixOn(on) {
      mixOn = !!on;
      root.classList.toggle("mix-off", !mixOn);
      lastZoom = 0;
      drawWave();
    }

    return { render, sync, zoom, setChain, setVoiceUrl, setVoiceOn, setMixOn, seek, isDragging: () => !!dragging };
  }

  global.LovTimeline = { create };
})(window);
