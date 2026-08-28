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

export async function fetchJson(url, opts) {
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
