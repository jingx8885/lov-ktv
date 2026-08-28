import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { openOverlay } from "../../ui/js/overlays.js";
import { paintMix } from "./mix.js";

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
      if (rtcState === "connected") $("micHint").textContent = "麦已接到电视";
      else if (rtcState === "failed") $("micHint").textContent = "电视没接上，再点一次开麦";
    },
  });
}

export function bindRoomRtc() {
  $("micToggle").onclick = async () => {
    const code = $("room").value.trim().toUpperCase();
    if (!code) {
      openOverlay("roomSheet");
      return showToast("先填房间码并点进入");
    }
    connectRoomRtc(code);
    const btn = $("micToggle");
    btn.disabled = true;
    $("micHint").dataset.hold = "1";
    try {
      if (state.roomRtc && state.roomRtc.isLive()) {
        await state.roomRtc.stopMic();
        $("micHint").textContent = "";
      } else {
        api.stopPhoneMic();
        $("micHint").textContent = "请允许使用麦克风";
        await state.roomRtc.startMic();
        $("micHint").textContent = "麦已打开，声音会从电视出来";
      }
    } catch (err) {
      $("micHint").textContent = LovMic.micErrorText(err);
    } finally {
      delete $("micHint").dataset.hold;
      btn.disabled = false;
      const live = !!(state.roomRtc && state.roomRtc.isLive());
      btn.classList.toggle("live", live);
      btn.classList.toggle("on", live);
      $("micGainRow").hidden = !live;
      btn.setAttribute("aria-label", live ? "关麦" : "开麦");
    }
  };
}

