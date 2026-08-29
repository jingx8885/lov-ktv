import { t } from "../../../shared/i18n/js/i18n.js";

export function hasNativeMic() {
  const bridge = window.LovKtvPhone;
  return !!(bridge && typeof bridge.capabilities === "function" && typeof bridge.startTvMic === "function");
}

export function nativeCaps() {
  if (!hasNativeMic()) return { native: false, tv: false, iem: false, host: "", port: 0, rate: 0 };
  try {
    return JSON.parse(window.LovKtvPhone.capabilities() || "{}");
  } catch (err) {
    return { native: false, tv: false, iem: false, host: "", port: 0, rate: 0 };
  }
}

export function nativeMicState() {
  if (!hasNativeMic()) return { tv: false, iem: false, gain: 100 };
  try {
    return JSON.parse(window.LovKtvPhone.state() || "{}");
  } catch (err) {
    return { tv: false, iem: false, gain: 100 };
  }
}

export function setNativeGain(value) {
  if (!hasNativeMic() || typeof window.LovKtvPhone.setGain !== "function") return;
  try {
    window.LovKtvPhone.setGain(Math.max(0, Math.min(100, Number(value) || 0)));
  } catch (err) {}
}

function waitMicPermission() {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("lovktv-mic-granted", onOk);
      window.removeEventListener("lovktv-mic-denied", onNo);
      clearTimeout(timer);
      if (ok) resolve();
      else reject(new Error(t("phone.mic.allow")));
    };
    const onOk = () => finish(true);
    const onNo = () => finish(false);
    const timer = setTimeout(() => finish(false), 25000);
    window.addEventListener("lovktv-mic-granted", onOk);
    window.addEventListener("lovktv-mic-denied", onNo);
  });
}

export async function nativeCall(method) {
  if (!hasNativeMic() || typeof window.LovKtvPhone[method] !== "function") {
    throw new Error(t("phone.mic.fail"));
  }
  let code = window.LovKtvPhone[method]();
  if (code === "ask") {
    await waitMicPermission();
    code = window.LovKtvPhone[method]();
  }
  if (code === "no-tv") throw new Error(t("phone.mic.needTv"));
  if (code === "ask") throw new Error(t("phone.mic.allow"));
  if (code !== "ok") throw new Error(t("phone.mic.fail"));
  return code;
}
