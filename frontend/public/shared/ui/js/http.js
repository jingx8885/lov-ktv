/**
 * @param {string} url
 * @param {RequestInit} [opts]
 * @returns {Promise<{ok: boolean, status: number, data: any}>}
 */
const MACHINE_KEY = "lovktv.machine";

function acceptLanguage() {
  if (typeof window !== "undefined" && window.LovI18n && window.LovI18n.acceptLanguage) {
    return window.LovI18n.acceptLanguage();
  }
  return "zh-CN";
}

export function machineId() {
  try {
    let id = localStorage.getItem(MACHINE_KEY) || "";
    if (id.length < 8) {
      id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/-/g, "");
      localStorage.setItem(MACHINE_KEY, id);
    }
    return id.slice(0, 64);
  } catch (_) {
    return "";
  }
}

function privateHttpHost(url) {
  try {
    const parsed = new URL(url, typeof location !== "undefined" ? location.href : undefined);
    if (parsed.protocol !== "http:") return false;
    const name = String(parsed.hostname || "")
      .trim()
      .toLowerCase();
    if (name === "localhost" || name.endsWith(".local")) return true;
    const parts = name.split(".");
    if (parts.length !== 4) return false;
    const nums = parts.map((part) => Number(part));
    if (nums.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return false;
    if (nums[0] === 192 && nums[1] === 168) return true;
    if (nums[0] === 10) return true;
    if (nums[0] === 172 && nums[1] >= 16 && nums[1] <= 31) return true;
    return false;
  } catch (_) {
    return false;
  }
}

function nativePhoneHttp() {
  try {
    return typeof window !== "undefined" && window.LovKtvPhone && typeof window.LovKtvPhone.http === "function";
  } catch (_) {
    return false;
  }
}

let httpSeq = 0;
const httpWait = {};

if (typeof window !== "undefined") {
  window.LovKtvOnHttp = function (msg) {
    const pending = msg && httpWait[msg.id];
    if (!pending) return;
    delete httpWait[msg.id];
    let data = {};
    try {
      data = typeof msg.body === "string" ? JSON.parse(msg.body || "{}") : msg.body || {};
    } catch (_) {
      data = {};
    }
    pending({ ok: !!msg.ok, status: Number(msg.status) || 0, data: data });
  };
  if (nativePhoneHttp()) window.__lovktvNativeLan = true;
}

function nativeFetchJson(url, opts) {
  const method = String((opts && opts.method) || "GET").toUpperCase();
  const body = opts && typeof opts.body === "string" ? opts.body : "";
  const id = String(++httpSeq);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      delete httpWait[id];
      reject(new Error("lan-timeout"));
    }, 20000);
    httpWait[id] = (hit) => {
      clearTimeout(timer);
      resolve(hit);
    };
    try {
      window.LovKtvPhone.http(id, url, method, body);
    } catch (err) {
      clearTimeout(timer);
      delete httpWait[id];
      reject(err);
    }
  });
}

export async function fetchJson(url, opts) {
  if (nativePhoneHttp() && privateHttpHost(url)) {
    return nativeFetchJson(url, opts);
  }
  const headers = new Headers((opts && opts.headers) || {});
  if (!headers.has("Accept-Language")) headers.set("Accept-Language", acceptLanguage());
  const mid = machineId();
  if (mid && !headers.has("X-LovKtv-Machine")) headers.set("X-LovKtv-Machine", mid);
  const res = await fetch(url, Object.assign({}, opts || {}, { credentials: "same-origin", headers }));
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  return { ok: res.ok, status: res.status, data };
}
