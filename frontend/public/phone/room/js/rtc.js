import { $ } from "../../../shared/ui/js/dom.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { openOverlay } from "../../ui/js/overlays.js";
import { paintMix } from "./mix.js?v=mix4";

export function connectRoomRtc(code) {
  code = String(code || "").trim().toUpperCase();
  if (!code || !window.LovMic) return;
  if (state.roomRtc && state.roomRtcCode === code) return;
  if (state.roomRtc) {
    state.roomRtc.stopMic().catch(() => {});
    state.roomRtc.disconnect();
  }
  state.roomRtcCode = code;
  state.roomRtc = LovMic.create({ role: "phone" });
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
    },
  });
}

export function bindRoomRtc() {
  const micToggle = $("micToggle");
  if (!micToggle) return;
  micToggle.onclick = async () => {
    const roomEl = $("room");
    const code = roomEl ? roomEl.value.trim().toUpperCase() : "";
    if (!code) {
      openOverlay("roomSheet");
      return showToast(t("phone.mic.needRoom"));
    }
    connectRoomRtc(code);
    const btn = micToggle;
    const micHint = $("micHint");
    btn.disabled = true;
    if (micHint) micHint.dataset.hold = "1";
    try {
      if (state.roomRtc && state.roomRtc.isLive()) {
        await state.roomRtc.stopMic();
        if (micHint) micHint.textContent = "";
      } else {
        api.stopPhoneMic();
        if (micHint) micHint.textContent = t("phone.mic.allow");
        await state.roomRtc.startMic();
        if (micHint) micHint.textContent = t("phone.mic.phoneOut");
      }
    } catch (err) {
      if (micHint) micHint.textContent = LovMic.micErrorText(err);
    } finally {
      if (micHint) delete micHint.dataset.hold;
      btn.disabled = false;
      const live = !!(state.roomRtc && state.roomRtc.isLive());
      btn.classList.toggle("live", live);
      btn.classList.toggle("on", live);
      if ($("micGainRow")) $("micGainRow").hidden = !live;
      btn.setAttribute("aria-label", live ? t("common.micOff") : t("common.micOn"));
    }
  };
}

