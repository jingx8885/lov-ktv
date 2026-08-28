/**
 * @param {string} url
 * @param {RequestInit} [opts]
 * @returns {Promise<{ok: boolean, status: number, data: any}>}
 */
function acceptLanguage() {
  if (typeof window !== "undefined" && window.LovI18n && window.LovI18n.acceptLanguage) {
    return window.LovI18n.acceptLanguage();
  }
  return "zh-CN";
}

export async function fetchJson(url, opts) {
  const headers = new Headers((opts && opts.headers) || {});
  if (!headers.has("Accept-Language")) headers.set("Accept-Language", acceptLanguage());
  const res = await fetch(url, { ...opts, headers });
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  return { ok: res.ok, status: res.status, data };
}
