import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";

export function micGainValue() {
  const hostMac = state.room && state.room.host_volume_kind === "mac";
  const vol = hostMac ? 1 : (((state.room && state.room.volume) != null ? state.room.volume : 80) / 100);
  const micGain = ((state.room && state.room.mic_gain) != null ? state.room.mic_gain : 80) / 100;
  return Math.max(0, Math.min(1, vol * micGain));
}

export function playRawMic(stream) {
  const el = $("liveMic");
  if (!el || !stream) return;
  if (el.srcObject !== stream) el.srcObject = stream;
  el.muted = false;
  el.volume = micGainValue();
  el.play().catch(() => {});
}

export async function bindLiveMic(stream) {
  state.pendingMic = stream;
  playRawMic(stream);
  api.applyMix();
  if (!window.LovAec) return;
  try {
    await LovAec.ensureCtx();
    const ctx = LovAec.getCtx();
    if (ctx && ctx.state === "suspended") await ctx.resume();
    const ok = await LovAec.attach(stream, {
      karaoke: $("karaoke"),
      vocal: $("vocal"),
      hook: state.audioHook,
      gain: micGainValue(),
    });
    api.applyMix();
    if (!ok) playRawMic(stream);
  } catch (err) {
    playRawMic(stream);
  }
}

export function clearLiveMic() {
  state.pendingMic = null;
  if (window.LovAec) LovAec.detach();
  const el = $("liveMic");
  el.pause();
  el.srcObject = null;
  $("micLive").hidden = true;
}

export function bindRoomRtc(code) {
  if (!window.LovMic || !code) return;
  if (state.roomRtc) return;
  state.roomRtc = LovMic.create({ role: "tv" });
  state.roomRtc.connect(code, {
    onSnapshot: (snap) => {
      if (!snap) return;
      state.room = snap;
      api.prefetchQueue(snap);
      api.applyMix();
      const now = snap.now_playing;
      if (now && now.status === "ready") {
        if (state.lastItem !== (now.id || now.song_id)) api.tick();
        else if (api.pageVisible() && state.isLeader) {
          const karaoke = $("karaoke");
          if (karaoke && karaoke.paused) api.startPlayback();
        }
      }
    },
    onRtc: (msg) => {
      if (msg.kind === "offer") state.roomRtc.handleOffer(msg);
      else if (msg.kind === "ice") state.roomRtc.addIce(msg);
      else if (msg.kind === "hangup") {
        state.roomRtc.resetPc();
        clearLiveMic();
        if (state.room) state.room.mic_on = false;
        api.applyMix();
      }
    },
    onStream: bindLiveMic,
  });
}

