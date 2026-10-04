// Page-side companion for /sw-media.js.
//
// The service worker caches versioned /media/ files in CacheStorage so the
// listen flow stops paying mobile data for every replay and seek. This module
// registers the worker, decides when extra prefetching is affordable, and
// exposes small helpers for diagnostics.

let registered = false;

function worker() {
  try {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null;
    return navigator.serviceWorker;
  } catch (err) {
    return null;
  }
}

/** Register /sw-media.js once per page. Safe to call from every mount. */
export function bootMediaCache() {
  if (registered) return;
  registered = true;
  const sw = worker();
  if (!sw) return;
  try {
    sw.register("/sw-media.js", { updateViaCache: "none" }).catch(() => {});
  } catch (err) {}
}

/**
 * True when a warm-up download is cheap: unmetered or unknown connection and
 * the user has not asked the browser to save data.
 */
function prefetchAffordable() {
  try {
    const conn = /** @type {any} */ (navigator).connection;
    if (!conn) return true; // no signal (iOS): allow, the SW dedupes anyway
    if (conn.saveData) return false;
    const type = String(conn.type || "");
    if (type === "cellular") return false;
    const downlink = Number(conn.downlink);
    if (isFinite(downlink) && downlink > 0 && downlink < 1) return false;
    return true;
  } catch (err) {
    return true;
  }
}

function send(payload) {
  const sw = worker();
  if (!sw) return;
  try {
    const post = (target) => target && target.postMessage(payload);
    if (sw.controller) {
      post(sw.controller);
      return;
    }
    if (sw.ready && sw.ready.then) {
      sw.ready.then((reg) => post(reg && reg.active)).catch(() => {});
    }
  } catch (err) {}
}

/**
 * Warm the cache for a song's media. The playing track is already in flight
 * through the worker; only alternate files are asked for here, and only when
 * prefetching is affordable.
 * @param {string[]} urls absolute or path /media/ URLs
 */
export function prefetchMedia(urls) {
  if (!prefetchAffordable()) return;
  send({ type: "lovktv-media-prefetch", urls: urls || [] });
}

/** Drop the whole media cache (used by diagnostics / storage pressure). */
export function clearMediaCache() {
  send({ type: "lovktv-media-clear" });
}
