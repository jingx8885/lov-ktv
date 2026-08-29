import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { openOverlay } from "../../../ui/js/overlays.js";
import { paintMix } from "./mix.js";
import {
  hasNativeMic,
  nativeCapabilities,
  nativeMicState,
  nativeCall,
  webMicApi,
  micErrorText
} from "../../../platform.js";

export function usesNativeMic() {
  return hasNativeMic();
}

function nativeError(err) {
  return micErrorText(err);
}

function nativeStartMic() {
  if (!hasNativeMic()) return Promise.reject(new Error(t("phone.mic.fail")));
  const caps = nativeCapabilities();
  if (!caps.host || !caps.port) return Promise.reject(new Error(t("phone.mic.needTv")));
  return nativeCall("startTvMic").catch((err) => {
    throw new Error(nativeError(err));
  });
}

function createNativeRtc() {
  return {
    peerId: "native",
    native: true,
    isLive() {
      return !!nativeMicState().tv;
    },
    startMic: nativeStartMic,
    async stopMic() {
      if (hasNativeMic()) await nativeCall("stopTvMic").catch(() => {});
    },
    disconnect() {
      if (hasNativeMic()) nativeCall("stopTvMic").catch(() => {});
    },
    connect() {},
    send() {},
    makeOffer: async () => {},
    handleAnswer: async () => {},
    handleOffer: async () => {},
    addIce: async () => {},
    resetPc: async () => {}
  };
}

export function connectRoomRtc(code) {
  code = String(code || "")
    .trim()
    .toUpperCase();
  if (!code) return;
  if (usesNativeMic()) {
    if (state.roomRtc && state.roomRtc.native && state.roomRtcCode === code) return;
    if (state.roomRtc) {
      state.roomRtc.stopMic().catch(() => {});
      state.roomRtc.disconnect();
    }
    state.roomRtcCode = code;
    state.roomRtc = createNativeRtc();
    return;
  }
  const webMic = webMicApi();
  if (!webMic) return;
  if (state.roomRtc && state.roomRtcCode === code) return;
  if (state.roomRtc) {
    state.roomRtc.stopMic().catch(() => {});
    state.roomRtc.disconnect();
  }
  state.roomRtcCode = code;
  state.roomRtc = webMic.create({ role: "phone" });
  state.roomRtc.connect(code, {
    onSnapshot: (room) => paintMix(room),
    onPeer: (msg) => {
      if (msg.event === "join" && msg.role === "tv" && state.roomRtc.isLive()) {
        state.roomRtc.makeOffer().catch(() => {});
      }
    },
    onRtc: (msg) => {
      if (msg.kind === "answer") state.roomRtc.handleAnswer(msg);
      else if (msg.kind === "ice") state.roomRtc.addIce(msg);
    },
    onState: (rtcState) => {
      if (!state.roomRtc.isLive()) return;
      const micHint = $("micHint");
      if (!micHint) return;
      if (rtcState === "connected") micHint.textContent = t("phone.mic.liveTv");
      else if (rtcState === "failed") micHint.textContent = t("phone.mic.tvFail");
    }
  });
}

function micFailText(err) {
  return micErrorText(err) || nativeError(err);
}

export function bindRoomRtc() {
  const micToggle = $("micToggle");
  if (!micToggle) return;
  micToggle.onclick = async () => {
    const roomEl = $("room");
    const code = roomEl ? roomEl.value.trim().toUpperCase() : "";
    if (usesNativeMic() && api.requestTvBind && api.requestTvBind()) {
      showToast(t("phone.mic.needTv"));
      return;
    }
    if (api.needTvOrRoom && api.needTvOrRoom()) return;
    if (!code) {
      openOverlay("roomSheet");
      return showToast(t("phone.mic.needRoom"));
    }
    connectRoomRtc(code);
    if (!state.roomRtc) {
      showToast(t("phone.mic.fail"));
      return;
    }
    const btn = micToggle;
    const micHint = $("micHint");
    if (btn.classList.contains("busy")) return;
    btn.classList.add("busy");
    btn.disabled = true;
    if (micHint) micHint.dataset.hold = "1";
    try {
      if (state.roomRtc.isLive()) {
        await state.roomRtc.stopMic();
        if (micHint) micHint.textContent = "";
        showToast(t("common.micOff"));
      } else {
        api.stopPhoneMic();
        if (micHint) micHint.textContent = t("phone.mic.allow");
        await state.roomRtc.startMic();
        if (micHint) micHint.textContent = t("phone.mic.phoneOut");
        showToast(t("phone.mic.opened"));
      }
    } catch (err) {
      const msg = micFailText(err);
      if (micHint) micHint.textContent = msg;
      showToast(msg);
    } finally {
      if (micHint) delete micHint.dataset.hold;
      btn.classList.remove("busy");
      btn.disabled = false;
      const live = !!(state.roomRtc && state.roomRtc.isLive());
      btn.classList.toggle("live", live);
      btn.classList.toggle("on", live);
      if ($("micGainRow")) $("micGainRow").hidden = !live;
      btn.setAttribute("aria-label", live ? t("common.micOff") : t("common.micOn"));
    }
  };
}
