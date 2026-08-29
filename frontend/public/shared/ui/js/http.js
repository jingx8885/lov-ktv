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
    const name = String(parsed.hostname || "").trim().toLowerCase();
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

if (typeof window !== "undefined") {
  window.LovKtvOnHttp = function (msg) {
    if (window.LovKtvPlatform && window.LovKtvPlatform.__onHttp) window.LovKtvPlatform.__onHttp(msg);
  };
}

export async function fetchJson(url, opts) {
  const platformHttp = typeof window !== "undefined" && window.LovKtvPlatform && window.LovKtvPlatform.http;
  if (platformHttp && platformHttp.fetchJson) {
    const native = platformHttp.fetchJson(url, opts);
    if (native) return native;
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
