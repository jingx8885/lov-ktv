import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";

export function liveCtxs() {
  const out = [];
  const aec = window.LovAec && LovAec.getCtx();
  if (aec) out.push(aec);
  if (state.audioHook && state.audioHook.ctx && out.indexOf(state.audioHook.ctx) < 0) out.push(state.audioHook.ctx);
  return out;
}

export function resumeCtxs() {
  return Promise.all(liveCtxs().map((ctx) => (
    ctx.state === "suspended" ? ctx.resume().catch(() => {}) : Promise.resolve()
  )));
}

export function hookAudio() {
  if (state.audioHook && state.audioHook.ctx) {
    if (state.audioHook.ctx.state === "suspended") state.audioHook.ctx.resume().catch(() => {});
    if (window.LovAec) LovAec.retap(state.audioHook);
    return;
  }
  if (!state.audioUnlocked) return;
  const shared = window.LovAec && LovAec.getCtx();
  state.audioHook = LovBands.hookAnalyser($("karaoke"), state.audioHook, shared ? { ctx: shared } : null);
  if (window.LovAec) LovAec.retap(state.audioHook);
}

export function unlockAudio() {
  state.audioUnlocked = true;
  api.startKeepAlive();
  if (window.LovAec) {
    LovAec.ensureCtx().then(() => {
      hookAudio();
      if (state.pendingMic) api.bindLiveMic(state.pendingMic);
    });
    return;
  }
  hookAudio();
}

export function playEl(el) {
  if (!el) return Promise.resolve();
  api.startKeepAlive();
  return resumeCtxs()
    .then(() => {
      const keep = $("keepAlive");
      return keep && keep.paused ? keep.play().catch(() => {}) : null;
    })
    .then(() => el.play())
    .catch(() => resumeCtxs().then(() => el.play()));
}

api.hookAudio = hookAudio;
api.unlockAudio = unlockAudio;
api.playEl = playEl;
api.resumeCtxs = resumeCtxs;
api.liveCtxs = liveCtxs;
