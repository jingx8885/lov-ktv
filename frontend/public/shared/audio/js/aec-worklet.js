// TV-side AEC.
// Keep the live mic. Subtract only the delayed speaker mix
// (karaoke + the voice the TV already played), i.e. the computer echo.

class LovAecProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    const sr = sampleRate || 48000;
    this.maxDelay = Math.floor(sr * 0.55);
    this.minDelay = Math.floor(sr * 0.1);
    this.delay = Math.floor(sr * 0.2);
    this.ref = new Float32Array(this.maxDelay + 256);
    this.wri = 0;
    this.order = 192;
    this.w = new Float32Array(this.order);
    this.mu = 0.08;
    this.eps = 1e-6;
    this.ds = Math.max(160, Math.round(sr / 100));
    this.envRef = new Float32Array(64);
    this.envMic = new Float32Array(64);
    this.envN = 0;
    this.envAccR = 0;
    this.envAccM = 0;
    this.envCount = 0;
    this.corrLeft = 0;
    this.freeze = 0;
    this.micRms = 0;
    this.spkRms = 0;
  }

  writeRef(sample) {
    this.ref[this.wri] = sample;
    this.wri++;
    if (this.wri >= this.ref.length) this.wri = 0;
  }

  readRef(offset) {
    let i = this.wri - offset;
    const n = this.ref.length;
    if (i < 0) i += n;
    return this.ref[i];
  }

  pushEnv(refAbs, micAbs) {
    this.envAccR += refAbs;
    this.envAccM += micAbs;
    this.envCount++;
    if (this.envCount < this.ds) return;
    const slot = this.envN % this.envRef.length;
    this.envRef[slot] = this.envAccR / this.envCount;
    this.envMic[slot] = this.envAccM / this.envCount;
    this.envN++;
    this.envAccR = 0;
    this.envAccM = 0;
    this.envCount = 0;
    this.corrLeft--;
    if (this.corrLeft <= 0 && this.envN > 24) {
      this.corrLeft = 12;
      this.estimateDelay();
    }
  }

  estimateDelay() {
    const n = this.envRef.length;
    const filled = Math.min(this.envN, n);
    if (filled < 20) return;
    const hop = this.ds;
    const minB = Math.max(1, Math.floor(this.minDelay / hop));
    const maxB = Math.min(filled - 8, Math.floor(this.maxDelay / hop));
    let best = 0;
    let bestAt = Math.floor(this.delay / hop);
    for (let d = minB; d <= maxB; d++) {
      let num = 0;
      let r2 = 0;
      let m2 = 0;
      const count = filled - d;
      for (let i = 0; i < count; i++) {
        const r = this.envRef[(this.envN - 1 - i - d + n * 8) % n];
        const m = this.envMic[(this.envN - 1 - i + n * 8) % n];
        num += r * m;
        r2 += r * r;
        m2 += m * m;
      }
      const den = Math.sqrt(r2 * m2) + 1e-8;
      const c = num / den;
      if (c > best) {
        best = c;
        bestAt = d;
      }
    }
    if (best < 0.2) return;
    const next = Math.max(this.minDelay, Math.min(this.maxDelay - this.order, bestAt * hop));
    this.delay = Math.round(this.delay * 0.7 + next * 0.3);
  }

  process(inputs, outputs) {
    const micIn = inputs[0] && inputs[0][0];
    const accIn = inputs[1] && inputs[1][0];
    const out = outputs[0] && outputs[0][0];
    if (!out) return true;
    const n = out.length;
    for (let i = 0; i < n; i++) {
      const raw = micIn ? micIn[i] : 0;
      const acc = accIn ? accIn[i] : 0;

      let yhat = 0;
      let pow = this.eps;
      let delayedAbs = 0;
      const base = this.delay;
      for (let k = 0; k < this.order; k++) {
        const x = this.readRef(base + k);
        yhat += this.w[k] * x;
        pow += x * x;
        delayedAbs += Math.abs(x);
      }
      delayedAbs /= this.order;

      const micAbs = Math.abs(raw);
      this.micRms = this.micRms * 0.996 + micAbs * 0.004;
      this.spkRms = this.spkRms * 0.996 + delayedAbs * 0.004;

      const liveVoice = this.micRms > 0.016 && micAbs > 1.4 * (Math.abs(yhat) + 0.008);
      if (liveVoice) this.freeze = 80;
      else if (this.freeze > 0) this.freeze--;

      const err = raw - yhat;
      if (this.freeze <= 0 && this.spkRms > 0.008 && pow > 1e-5) {
        const step = (this.mu * err) / pow;
        for (let k = 0; k < this.order; k++) {
          this.w[k] += step * this.readRef(base + k);
        }
      }

      const maxEcho = delayedAbs * 2.4 + 0.004;
      let echo = yhat;
      if (echo > maxEcho) echo = maxEcho;
      else if (echo < -maxEcho) echo = -maxEcho;
      const cleaned = raw - echo;
      out[i] = cleaned;

      const played = acc + cleaned;
      this.writeRef(played);
      this.pushEnv(Math.abs(played), micAbs);
    }
    return true;
  }
}

registerProcessor("lov-aec", LovAecProcessor);
