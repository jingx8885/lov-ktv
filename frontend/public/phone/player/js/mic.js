import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { showActionSheet } from "../../ui/js/overlays.js";
import { hookPlayerAudio, applyPlayerVocalMix } from "./playback.js";

export function phoneMicHintIdle() {
  return state.phoneIem
    ? "戴有线耳机。耳返会关掉回声消除，自己的声音才会快。蓝牙耳机会再慢一截。"
    : "本机唱歌，伴奏和人声一起从手机喇叭出来。回音大就打开耳返。";
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
  let last = null;
  for (const audio of phoneMicAudioConstraints()) {
    try {
      return await navigator.mediaDevices.getUserMedia({ audio, video: false });
    } catch (err) {
      last = err;
    }
  }
  throw last || new Error("开麦失败");
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
  const on = !!(state.phoneMic && state.phoneMic.getTracks().some((track) => track.readyState === "live"));
  $("playerMic").classList.toggle("on", on);
  $("playerMic").classList.toggle("live", on);
  $("playerMic").setAttribute("aria-label", on ? "关麦" : "开麦唱歌");
  $("playerMicLabel").textContent = on ? "开麦中" : "开麦";
  $("playerMicRow").hidden = !on;
  $("playerKtv").classList.toggle("live", on);
  $("playerIem").classList.toggle("on", state.phoneIem);
  $("playerIem").setAttribute("aria-pressed", state.phoneIem ? "true" : "false");
  $("playerArt").classList.toggle("is-sing", on);
  if (!on && !$("playerMicHint").dataset.hold) {
    $("playerMicHint").textContent = phoneMicHintIdle();
  }
}

export function setPhoneMicGain(value) {
  state.phoneMicLevel = Math.max(0, Math.min(100, Number(value) || 0));
  localStorage.setItem("phoneMicGain", String(state.phoneMicLevel));
  $("playerMicGain").value = String(state.phoneMicLevel);
  $("playerMicVal").textContent = String(state.phoneMicLevel);
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

export async function startPhoneMic(opts) {
  const restart = !!(opts && opts.restart);
  if (!restart && state.roomRtc && state.roomRtc.isLive()) {
    await state.roomRtc.stopMic();
    $("micHint").textContent = "";
    $("micToggle").classList.remove("live", "on");
    $("micGainRow").hidden = true;
  }
  const jack = await headphoneState();
  if (!restart && state.phoneIem && jack.kind === "speaker") {
    const go = await showActionSheet({
      title: "先戴上耳机",
      message: "喇叭外放会把伴奏灌回麦克风。还没戴也要开麦？",
      confirm: "继续开麦",
    });
    if (!go) throw new Error("先戴上耳机再开麦");
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
    $("playerMicHint").textContent = "耳返已开：回声消除已关，有线耳机听自己会快很多。麦声拉到 0 就只听伴奏";
  } else if (state.phoneIem) {
    $("playerMicHint").textContent = "耳返已开。请用有线耳机；蓝牙还会慢一截。麦声拉到 0 就只听伴奏";
  } else {
    $("playerMicHint").textContent = "麦已打开，人声和伴奏从这只手机出来";
  }
}

export function bindPhoneMic() {
  paintPhoneMic();
  $("playerMicGain").value = String(state.phoneMicLevel);
  $("playerMicVal").textContent = String(state.phoneMicLevel);
  $("playerMicGain").oninput = () => setPhoneMicGain($("playerMicGain").value);
  $("playerIem").onclick = async () => {
    state.phoneIem = !state.phoneIem;
    localStorage.setItem("phoneIem", state.phoneIem ? "1" : "0");
    paintPhoneMic();
    if (!state.phoneMic) return;
    $("playerMicHint").dataset.hold = "1";
    try {
      await startPhoneMic({ restart: true });
    } catch (err) {
      stopPhoneMic();
      $("playerMicHint").textContent = (err && err.message) || "耳返切换失败";
    } finally {
      delete $("playerMicHint").dataset.hold;
      paintPhoneMic();
    }
  };
  $("playerMic").onclick = async () => {
    const btn = $("playerMic");
    btn.disabled = true;
    $("playerMicHint").dataset.hold = "1";
    try {
      if (state.phoneMic) {
        stopPhoneMic();
        $("playerMicHint").textContent = phoneMicHintIdle();
      } else {
        $("playerMicHint").textContent = state.phoneIem ? "戴上耳机，并允许使用麦克风" : "请允许使用麦克风";
        await startPhoneMic();
      }
    } catch (err) {
      stopPhoneMic();
      $("playerMicHint").textContent = (window.LovMic && LovMic.micErrorText(err)) || (err && err.message) || "开麦失败";
    } finally {
      delete $("playerMicHint").dataset.hold;
      btn.disabled = false;
      paintPhoneMic();
    }
  };
}

api.ensurePhoneCtx = ensurePhoneCtx;
api.stopPhoneMic = stopPhoneMic;
api.paintPhoneMic = paintPhoneMic;
