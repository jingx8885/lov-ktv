import { $ } from "../../../shared/ui/js/dom.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { showActionSheet } from "../../ui/js/overlays.js";
import { hookPlayerAudio, applyPlayerVocalMix } from "./controls.js";
import { hasNativeMic, nativeCaps, nativeCall, nativeMicState, setNativeGain } from "../../room/js/native-mic.js";
import { micErrorText as platformMicErrorText } from "../../platform.js";

const MIC_WAIT_MS = 12000;

function micErrorText(err) {
  return platformMicErrorText(err);
}

function holdMicHint(on, text) {
  const hint = $("playerMicHint");
  const dock = $("playerKtv");
  if (hint) {
    if (on) hint.dataset.hold = "1";
    else delete hint.dataset.hold;
    if (text != null) hint.textContent = text;
  }
  if (dock) dock.classList.toggle("is-hint", !!(on || (hint && hint.dataset.hold)));
}

function withTimeout(task, ms) {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(t("phone.mic.fail"))), ms);
    Promise.resolve()
      .then(task)
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch((err) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

export function phoneMicHintIdle() {
  return state.phoneIem ? t("phone.mic.idleIem") : t("phone.mic.idleSpeaker");
}

export function ensurePhoneCtx() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (state.phoneCtx && state.phoneCtx.state !== "closed") return state.phoneCtx;
  if (state.playerHook && state.playerHook.ctx && state.playerHook.ctx.state !== "closed") {
    state.phoneCtx = state.playerHook.ctx;
    return state.phoneCtx;
  }
  state.phoneCtx = new AC({ latencyHint: "interactive" });
  return state.phoneCtx;
}

export function phoneMicAudioConstraints() {
  if (state.phoneIem) {
    return [
      { echoCancellation: false, noiseSuppression: false, autoGainControl: false, latency: 0.01, channelCount: 1 },
      { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    ];
  }
  return [{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }];
}

export async function acquirePhoneMic() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error(t("mic.noDevice"));
  }
  return withTimeout(async () => {
    let last = null;
    for (const audio of phoneMicAudioConstraints()) {
      try {
        return await navigator.mediaDevices.getUserMedia({ audio, video: false });
      } catch (err) {
        last = err;
      }
    }
    throw last || new Error(t("phone.mic.fail"));
  }, MIC_WAIT_MS);
}

export function disconnectPhoneMicGraph() {
  if (state.phoneMicSrc) try { state.phoneMicSrc.disconnect(); } catch (err) {}
  if (state.phoneMicGain) try { state.phoneMicGain.disconnect(); } catch (err) {}
  state.phoneMicSrc = state.phoneMicGain = null;
  const el = $("phoneIemVoice");
  if (el) {
    el.pause();
    el.srcObject = null;
  }
}

export function applyPhoneMonitor() {
  disconnectPhoneMicGraph();
  if (!state.phoneMic) return;
  const el = $("phoneIemVoice");
  if (state.phoneIem && el) {
    el.srcObject = state.phoneMic;
    el.muted = false;
    el.volume = Math.max(0, Math.min(1, state.phoneMicLevel / 100));
    el.play().catch(() => {});
    return;
  }
  if (!state.phoneCtx) return;
  state.phoneMicSrc = state.phoneCtx.createMediaStreamSource(state.phoneMic);
  state.phoneMicGain = state.phoneCtx.createGain();
  state.phoneMicGain.gain.value = state.phoneMicLevel / 100;
  state.phoneMicSrc.connect(state.phoneMicGain);
  state.phoneMicGain.connect(state.phoneCtx.destination);
}

export function paintPhoneMic() {
  const btn = $("playerMic");
  if (!btn) return;
  const on = !!(state.phoneNativeLive || (state.phoneMic && state.phoneMic.getTracks().some((track) => track.readyState === "live")));
  btn.classList.toggle("on", on);
  btn.classList.toggle("live", on);
  btn.setAttribute("aria-label", on ? t("common.micOff") : t("phone.player.micSing"));
  if ($("playerMicLabel")) $("playerMicLabel").textContent = on ? t("phone.player.micOn") : t("common.micOn");
  if ($("playerMicRow")) $("playerMicRow").hidden = !on;
  if ($("playerKtv")) $("playerKtv").classList.toggle("live", on);
  if ($("playerIem")) {
    $("playerIem").classList.toggle("on", state.phoneIem);
    $("playerIem").setAttribute("aria-pressed", state.phoneIem ? "true" : "false");
  }
  if ($("playerArt")) $("playerArt").classList.toggle("is-sing", on);
  const hint = $("playerMicHint");
  if (hint && !on && !hint.dataset.hold) hint.textContent = phoneMicHintIdle();
}

export function setPhoneMicGain(value) {
  state.phoneMicLevel = Math.max(0, Math.min(100, Number(value) || 0));
  localStorage.setItem("phoneMicGain", String(state.phoneMicLevel));
  $("playerMicGain").value = String(state.phoneMicLevel);
  $("playerMicVal").textContent = String(state.phoneMicLevel);
  setNativeGain(state.phoneMicLevel);
  if (state.phoneMicGain) state.phoneMicGain.gain.value = state.phoneMicLevel / 100;
  const el = $("phoneIemVoice");
  if (el) el.volume = Math.max(0, Math.min(1, state.phoneMicLevel / 100));
}

export function stopPhoneMic() {
  disconnectPhoneMicGraph();
  if (state.phoneMic) {
    state.phoneMic.getTracks().forEach((track) => track.stop());
    state.phoneMic = null;
  }
  if (hasNativeMic() && (state.phoneNativeLive || nativeMicState().iem)) {
    nativeCall("stopIem").catch(() => {});
    if (state.phoneStartedTv) {
      nativeCall("stopTvMic").catch(() => {});
      state.phoneStartedTv = false;
    }
  }
  state.phoneNativeLive = false;
  paintPhoneMic();
}

export async function headphoneState() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return { kind: "unknown", sink: "" };
  const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
  const outs = devices.filter((item) => item.kind === "audiooutput");
  const hp = outs.find((item) => /headphone|headset|airpod|earbud|earphone|usb audio|lightning|耳机|耳麦/i.test(item.label || ""));
  if (hp) return { kind: "headphones", sink: hp.deviceId || "" };
  const text = outs.map((item) => item.label || "").join(" ").toLowerCase();
  if (outs.length && /speaker|扬声器/.test(text) && !/head|ear|耳机/.test(text)) {
    return { kind: "speaker", sink: "" };
  }
  return { kind: "unknown", sink: "" };
}

export async function routePhoneSink(sink) {
  if (!sink) return false;
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  try {
    if (audio && audio.setSinkId) await audio.setSinkId(sink);
    if (guide && guide.setSinkId) await guide.setSinkId(sink);
    const iem = $("phoneIemVoice");
    if (iem && iem.setSinkId) await iem.setSinkId(sink);
    if (state.phoneCtx && state.phoneCtx.setSinkId) await state.phoneCtx.setSinkId(sink);
    return true;
  } catch (err) {
    return false;
  }
}

async function startNativePhoneMic() {
  const caps = nativeCaps();
  if (state.phoneIem) {
    await nativeCall("startIem");
  } else if (nativeMicState().iem) {
    await nativeCall("stopIem");
  }
  if (caps.tv && !nativeMicState().tv) {
    await nativeCall("startTvMic");
    state.phoneStartedTv = true;
  }
  setNativeGain(state.phoneMicLevel);
  state.phoneNativeLive = true;
  paintPhoneMic();
  if (state.phoneIem) {
    $("playerMicHint").textContent = t("phone.mic.hintNativeIem");
  } else if (caps.tv) {
    $("playerMicHint").textContent = t("phone.mic.hintNativeTv");
  } else {
    $("playerMicHint").textContent = t("phone.mic.hintSpeaker");
  }
}

export async function startPhoneMic(opts) {
  const restart = !!(opts && opts.restart);
  if (!restart && state.roomRtc && state.roomRtc.isLive()) {
    await state.roomRtc.stopMic();
    if ($("micHint")) $("micHint").textContent = "";
    if ($("micToggle")) $("micToggle").classList.remove("live", "on");
    if ($("micGainRow")) $("micGainRow").hidden = true;
  }
  const jack = await headphoneState();
  if (!restart && state.phoneIem && jack.kind === "speaker") {
    const go = await showActionSheet({
      title: t("phone.mic.headphoneTitle"),
      message: t("phone.mic.headphoneMsg"),
      confirm: t("phone.mic.headphoneGo"),
    });
    if (!go) throw new Error(t("phone.mic.headphoneNeed"));
  }
  if (hasNativeMic()) {
    await startNativePhoneMic();
    return;
  }
  hookPlayerAudio();
  state.phoneCtx = ensurePhoneCtx();
  if (state.phoneCtx && state.phoneCtx.state === "suspended") await state.phoneCtx.resume();
  if (state.phoneMic) {
    state.phoneMic.getTracks().forEach((track) => track.stop());
    state.phoneMic = null;
  }
  disconnectPhoneMicGraph();
  state.phoneMic = await acquirePhoneMic();
  applyPhoneMonitor();
  if (state.phoneIem && jack.sink) await routePhoneSink(jack.sink);
  applyPlayerVocalMix();
  paintPhoneMic();
  if (state.phoneIem && jack.kind === "headphones") {
    $("playerMicHint").textContent = t("phone.mic.hintIemWired");
  } else if (state.phoneIem) {
    $("playerMicHint").textContent = t("phone.mic.hintIemBt");
  } else {
    $("playerMicHint").textContent = t("phone.mic.hintSpeaker");
  }
}

export function bindPhoneMic() {
  const btn = $("playerMic");
  if (!btn) return;
  paintPhoneMic();
  if ($("playerMicGain")) {
    $("playerMicGain").value = String(state.phoneMicLevel);
    $("playerMicVal").textContent = String(state.phoneMicLevel);
    $("playerMicGain").oninput = () => setPhoneMicGain($("playerMicGain").value);
  }
  if ($("playerIem")) $("playerIem").onclick = async () => {
    state.phoneIem = !state.phoneIem;
    localStorage.setItem("phoneIem", state.phoneIem ? "1" : "0");
    paintPhoneMic();
    if (!state.phoneMic && !state.phoneNativeLive) return;
    holdMicHint(true, t("phone.mic.allowIem"));
    try {
      await startPhoneMic({ restart: true });
      holdMicHint(false);
      showToast(t("phone.mic.opened"));
    } catch (err) {
      stopPhoneMic();
      const msg = micErrorText(err) || t("phone.mic.iemFail");
      holdMicHint(true, msg);
      showToast(msg);
    } finally {
      paintPhoneMic();
    }
  };
  btn.onclick = async () => {
    if (btn.classList.contains("busy")) return;
    btn.classList.add("busy");
    try {
      if (state.phoneMic) {
        stopPhoneMic();
        holdMicHint(false, phoneMicHintIdle());
        showToast(t("common.micOff"));
      } else {
        holdMicHint(true, state.phoneIem ? t("phone.mic.allowIem") : t("phone.mic.allow"));
        await startPhoneMic();
        holdMicHint(false);
        showToast(t("phone.mic.opened"));
      }
    } catch (err) {
      stopPhoneMic();
      const msg = micErrorText(err);
      holdMicHint(true, msg);
      showToast(msg);
    } finally {
      btn.classList.remove("busy");
      paintPhoneMic();
    }
  };
}

