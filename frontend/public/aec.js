(function (global) {
  let ctx = null;
  let workletReady = null;
  let node = null;
  let micSrc = null;
  let refMix = null;
  let outGain = null;
  let karaokeTap = null;
  let vocalTap = null;
  let hookTap = null;
  let active = false;
  let stream = null;

  function Ctx() {
    return global.AudioContext || global.webkitAudioContext;
  }

  function ensureCtx() {
    const AC = Ctx();
    if (!AC) return Promise.resolve(null);
    if (ctx && ctx.state !== "closed") {
      if (ctx.state === "suspended") ctx.resume().catch(() => {});
      return workletReady || Promise.resolve(ctx);
    }
    ctx = new AC();
    workletReady = ctx.audioWorklet
      .addModule("/aec-worklet.js?v=aec4")
      .then(() => ctx)
      .catch(() => {
        workletReady = null;
        return null;
      });
    return workletReady;
  }

  function getCtx() {
    return ctx && ctx.state !== "closed" ? ctx : null;
  }

  function isActive() {
    return active;
  }

  function disconnect(item) {
    if (!item) return;
    try { item.disconnect(); } catch (err) {}
  }

  function clearGraph() {
    disconnect(micSrc);
    disconnect(node);
    disconnect(outGain);
    disconnect(karaokeTap);
    disconnect(vocalTap);
    disconnect(hookTap);
    disconnect(refMix);
    micSrc = node = outGain = karaokeTap = vocalTap = hookTap = refMix = null;
    active = false;
  }

  function tapCapture(el) {
    if (!ctx || !el || typeof el.captureStream !== "function") return null;
    try {
      const media = el.captureStream();
      if (!media.getAudioTracks().length) return null;
      return ctx.createMediaStreamSource(media);
    } catch (err) {
      return null;
    }
  }

  function retap(hook) {
    if (!ctx || !refMix || hookTap || !hook || !hook.source || hook.ctx !== ctx) return;
    hookTap = ctx.createGain();
    hookTap.gain.value = 1;
    hook.source.connect(hookTap);
    hookTap.connect(refMix);
  }

  function setGain(value) {
    if (outGain) outGain.gain.value = Math.max(0, Math.min(1, Number(value) || 0));
  }

  async function attach(next, opts) {
    stream = next;
    const ready = await ensureCtx();
    if (!ready || !next) return false;
    if (ctx.state === "suspended") {
      try { await ctx.resume(); } catch (err) {}
    }
    if (ctx.state === "suspended") return false;
    clearGraph();
    try {
      node = new AudioWorkletNode(ctx, "lov-aec", {
        numberOfInputs: 2,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        channelCount: 1,
        channelCountMode: "explicit",
      });
    } catch (err) {
      return false;
    }
    refMix = ctx.createGain();
    refMix.gain.value = 1;
    micSrc = ctx.createMediaStreamSource(next);
    micSrc.connect(node, 0, 0);
    refMix.connect(node, 0, 1);
    karaokeTap = tapCapture(opts && opts.karaoke);
    vocalTap = tapCapture(opts && opts.vocal);
    if (karaokeTap) karaokeTap.connect(refMix);
    if (vocalTap) vocalTap.connect(refMix);
    retap(opts && opts.hook);
    outGain = ctx.createGain();
    outGain.gain.value = opts && opts.gain != null ? opts.gain : 1;
    node.connect(outGain);
    outGain.connect(ctx.destination);
    active = true;
    return true;
  }

  function detach() {
    clearGraph();
    stream = null;
  }

  global.LovAec = { ensureCtx, getCtx, attach, detach, retap, setGain, isActive };
})(window);
