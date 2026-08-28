/**
 * @param {string} url
 * @param {RequestInit} [opts]
 * @returns {Promise<{ok: boolean, status: number, data: any}>}
 */
export async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  return { ok: res.ok, status: res.status, data };
}
