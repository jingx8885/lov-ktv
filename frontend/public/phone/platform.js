/**
 * Phone platform boundary.
 *
 * The web desk and the Android WebView expose the same ports.  Feature
 * modules must use these capability-shaped helpers instead of reaching into
 * the injected bridge or guessing whether LAN HTTP has been installed.
 */
import { t } from "../shared/i18n/js/i18n.js";

function bridge() {
  try {
    return typeof window !== "undefined" ? window.LovKtvPhone || null : null;
  } catch (_) {
    return null;
  }
}

function privateHttpHost(url) {
  try {
    const parsed = new URL(url, typeof location !== "undefined" ? location.href : undefined);
    if (parsed.protocol !== "http:") return false;
    const host = String(parsed.hostname || "").toLowerCase();
    if (host === "localhost" || host.endsWith(".local")) return true;
    const parts = host.split(".");
    if (parts.length !== 4) return false;
    const nums = parts.map((part) => Number(part));
    if (nums.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return false;
    return (
      (nums[0] === 192 && nums[1] === 168) || nums[0] === 10 || (nums[0] === 172 && nums[1] >= 16 && nums[1] <= 31)
    );
  } catch (_) {
    return false;
  }
}

export function hasNativePhone() {
  return !!bridge();
}

export function nativeCapabilities() {
  const native = bridge();
  if (!native || typeof native.capabilities !== "function") {
    return { native: false, tv: false, iem: false, host: "", port: 0, rate: 0 };
  }
  try {
    return JSON.parse(native.capabilities() || "{}");
  } catch (_) {
    return { native: false, tv: false, iem: false, host: "", port: 0, rate: 0 };
  }
}

export function nativeMicState() {
  const native = bridge();
  if (!native || typeof native.state !== "function") return { tv: false, iem: false, gain: 100 };
  try {
    return JSON.parse(native.state() || "{}");
  } catch (_) {
    return { tv: false, iem: false, gain: 100 };
  }
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

/** Call an Android phone bridge method, including its permission handshake. */
export async function nativeCall(method) {
  const native = bridge();
  if (!native || typeof native[method] !== "function") throw new Error(t("phone.mic.fail"));
  let code = native[method]();
  if (code === "ask") {
    await waitMicPermission();
    code = native[method]();
  }
  if (code === "no-tv") throw new Error(t("phone.mic.needTv"));
  if (code === "ask") throw new Error(t("phone.mic.allow"));
  if (code !== "ok") throw new Error(t("phone.mic.fail"));
  return code;
}

export function setNativeGain(value) {
  const native = bridge();
  if (!native || typeof native.setGain !== "function") return;
  try {
    native.setGain(Math.max(0, Math.min(100, Number(value) || 0)));
  } catch (_) {}
}

export function hasNativeMic() {
  const native = bridge();
  return !!(native && typeof native.capabilities === "function" && typeof native.startTvMic === "function");
}

export function hasNativeScan() {
  const native = bridge();
  return !!(native && typeof native.scanTv === "function");
}

export function scanTv() {
  const native = bridge();
  if (!native || typeof native.scanTv !== "function") return false;
  try {
    native.scanTv();
    return true;
  } catch (_) {
    return false;
  }
}

export function useLan(lan, room) {
  const native = bridge();
  if (!native || typeof native.useLan !== "function") return false;
  try {
    native.useLan(String(lan || ""), String(room || ""));
    return true;
  } catch (_) {
    return false;
  }
}

let httpSeq = 0;
const pendingHttp = {};

function nativeHttpAvailable() {
  const native = bridge();
  return !!(native && typeof native.http === "function");
}

function nativeFetchJson(url, opts) {
  const native = bridge();
  const id = String(++httpSeq);
  const method = String((opts && opts.method) || "GET").toUpperCase();
  const body = opts && typeof opts.body === "string" ? opts.body : "";
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      delete pendingHttp[id];
      reject(new Error("lan-timeout"));
    }, 20000);
    pendingHttp[id] = (msg) => {
      clearTimeout(timer);
      delete pendingHttp[id];
      let data = {};
      try {
        data = typeof msg.body === "string" ? JSON.parse(msg.body || "{}") : msg.body || {};
      } catch (_) {}
      resolve({ ok: !!msg.ok, status: Number(msg.status) || 0, data });
    };
    try {
      native.http(id, url, method, body);
    } catch (err) {
      clearTimeout(timer);
      delete pendingHttp[id];
      reject(err);
    }
  });
}

export const phonePlatform = {
  mic: {
    hasNative: hasNativeMic,
    capabilities: nativeCapabilities,
    state: nativeMicState,
    call: nativeCall,
    setGain: setNativeGain
  },
  scanner: { available: hasNativeScan, scan: scanTv, useLan },
  media: {
    url(path) {
      return String(path || "");
    }
  },
  remote: {
    open(url) {
      try {
        return !!window.open(url, "lovktv-tv");
      } catch (_) {
        return false;
      }
    }
  },
  http: {
    available: nativeHttpAvailable,
    isLan: privateHttpHost,
    fetchJson(url, opts) {
      return nativeHttpAvailable() && privateHttpHost(url) ? nativeFetchJson(url, opts) : null;
    }
  }
};

/** Install a host-provided port bundle for mount(root, deps) tests/embedders. */
export function installPlatform(next) {
  if (!next || typeof next !== "object") return phonePlatform;
  Object.assign(phonePlatform, next);
  if (typeof window !== "undefined") window.LovKtvPlatform = phonePlatform;
  return phonePlatform;
}

phonePlatform.__onHttp = function (msg) {
  const pending = pendingHttp[msg && msg.id];
  if (pending) pending(msg);
};

// Shared HTTP code discovers the port through this neutral capability object.
if (typeof window !== "undefined") window.LovKtvPlatform = phonePlatform;

export function lanFetchReady() {
  return !!(typeof window !== "undefined" && window.__lovktvLanFetch);
}

export function nativeHttpReady() {
  return nativeHttpAvailable();
}

export function webMicApi() {
  try {
    return typeof window !== "undefined" ? window.LovMic || null : null;
  } catch (_) {
    return null;
  }
}

export function micErrorText(err) {
  const api = webMicApi();
  try {
    return (
      (api && typeof api.micErrorText === "function" && api.micErrorText(err)) ||
      (err && err.message) ||
      t("phone.mic.fail")
    );
  } catch (_) {
    return (err && err.message) || t("phone.mic.fail");
  }
}
