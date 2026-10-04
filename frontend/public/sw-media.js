// lov-ktv media cache service worker.
//
// Phone/TV listening streams song assets from /media/{song}/{file}?v={rev}.
// Browsers only keep the media element's byte-range reads in a memory-only
// media cache, so every track costs a full mobile download. This worker
// persists versioned media files in CacheStorage so replays and seeks are
// served locally. Unversioned URLs (lyrics can change without a rev) and
// anything outside /media/ always pass through to the network.

const CACHE = "lovktv-media-v1";
const DEFAULT_BUDGET = 1536 * 1024 * 1024; // 1.5 GiB across all songs
const MAX_FILE = 512 * 1024 * 1024;
const BUDGET = Number(self.LOVKTV_MEDIA_BUDGET) || DEFAULT_BUDGET;
const INDEX_KEY = self.location.origin + "/__lovktv_media_index__";

// One index entry per song: { at, size, files: { name: { key, size } } }.
// CacheStorage has no metadata API, so the index itself is stored as a
// cached response.
let indexPromise = null;
const pending = new Map(); // url -> in-flight download record
let indexChain = Promise.resolve();

function isMediaPath(pathname) {
  const parts = pathname.split("/");
  return parts[1] === "media" && parts.length === 4 && !!parts[2] && !!parts[3];
}

function mediaParts(url) {
  try {
    const parts = new URL(url).pathname.split("/");
    return {
      song: decodeURIComponent(parts[2] || ""),
      name: parts[3] || ""
    };
  } catch (err) {
    return { song: "", name: "" };
  }
}

function hasRev(url) {
  try {
    return !!new URL(url).searchParams.get("v");
  } catch (err) {
    return false;
  }
}

function parseRange(header, size) {
  if (!header) return null;
  const eq = String(header).indexOf("=");
  if (eq < 0 || header.slice(0, eq).trim() !== "bytes") return null;
  const first = header
    .slice(eq + 1)
    .split(",")[0]
    .trim();
  const dash = first.indexOf("-");
  if (dash < 0) return null;
  const left = first.slice(0, dash).trim();
  const right = first.slice(dash + 1).trim();
  let start;
  let end;
  if (left === "") {
    const suffix = parseInt(right, 10);
    if (!isFinite(suffix) || suffix <= 0) return null;
    if (suffix >= size) return { start: 0, end: size - 1 };
    return { start: size - suffix, end: size - 1 };
  }
  start = parseInt(left, 10);
  if (!isFinite(start) || start < 0) return null;
  end = right === "" ? size - 1 : Math.min(parseInt(right, 10), size - 1);
  if (!isFinite(end)) return null;
  return { start, end };
}

function ranged(blob, range) {
  const size = blob.size;
  if (!range) return new Response(blob); // malformed range: ignore it
  if (range.start >= size || range.end < range.start) {
    return new Response(null, {
      status: 416,
      headers: { "Content-Range": "bytes */" + size }
    });
  }
  const end = Math.min(range.end, size - 1);
  const part = blob.slice(range.start, end + 1);
  return new Response(part, {
    status: 206,
    headers: {
      "Content-Type": part.type || "application/octet-stream",
      "Content-Range": "bytes " + range.start + "-" + end + "/" + size,
      "Content-Length": String(part.size),
      "Accept-Ranges": "bytes"
    }
  });
}

async function loadIndex(cache) {
  if (!indexPromise) {
    indexPromise = cache
      .match(INDEX_KEY)
      .then(function (res) {
        return res ? res.json() : {};
      })
      .catch(function () {
        return {};
      });
  }
  return indexPromise;
}

function saveIndex(cache, index) {
  indexChain = indexChain
    .catch(function () {})
    .then(function () {
      return cache.put(
        INDEX_KEY,
        new Response(JSON.stringify(index), {
          headers: { "Content-Type": "application/json" }
        })
      );
    })
    .catch(function () {});
  return indexChain;
}

async function touch(cache, key, parts) {
  const index = await loadIndex(cache);
  const entry = index[parts.song] || (index[parts.song] = { at: 0, size: 0, files: {} });
  entry.at = Date.now();
  if (!entry.files[parts.name]) entry.files[parts.name] = { key: key, size: 0 };
  saveIndex(cache, index);
}

async function putBlob(cache, key, parts, blob) {
  if (blob.size <= 0 || blob.size > MAX_FILE) return;
  await cache.put(key, new Response(blob));
  const index = await loadIndex(cache);
  const entry = index[parts.song] || (index[parts.song] = { at: 0, size: 0, files: {} });
  const prev = entry.files[parts.name];
  if (prev) entry.size -= prev.size || 0;
  entry.files[parts.name] = { key: key, size: blob.size };
  entry.size += blob.size;
  entry.at = Date.now();
  saveIndex(cache, index);
  await evict(cache, index, parts.song);
}

async function evict(cache, index, keepSong) {
  let total = 0;
  const songs = [];
  for (const song in index) {
    const entry = index[song];
    if (!entry || !entry.files) continue;
    songs.push({ song: song, at: entry.at || 0, size: entry.size || 0 });
    total += entry.size || 0;
  }
  songs.sort(function (a, b) {
    return a.at - b.at;
  });
  for (const row of songs) {
    if (total <= BUDGET) break;
    if (row.song === keepSong) continue;
    const entry = index[row.song];
    for (const name in entry.files) {
      await cache.delete(entry.files[name].key).catch(function () {});
    }
    delete index[row.song];
    total -= row.size;
  }
  saveIndex(cache, index);
}

// Copy [pos, limit) out of the download's buffered chunks without
// disturbing them; other in-flight range responses share the buffer.
function take(dl, pos, limit) {
  const buf = dl.buf;
  const start = dl.bufStart;
  if (pos < start) pos = start;
  if (limit > start + dl.bufLen) limit = start + dl.bufLen;
  const out = new Uint8Array(limit - pos);
  let offset = start;
  let wrote = 0;
  for (let i = 0; i < buf.length; i += 1) {
    const chunk = buf[i];
    const chunkEnd = offset + chunk.length;
    if (chunkEnd > pos && offset < limit) {
      const from = Math.max(0, pos - offset);
      const to = Math.min(chunk.length, limit - offset);
      out.set(chunk.subarray(from, to), wrote);
      wrote += to - from;
    }
    offset = chunkEnd;
  }
  return out.subarray(0, wrote);
}

function wake(dl) {
  const waiters = dl.waiters;
  dl.waiters = [];
  for (const fn of waiters) fn();
}

async function pump(dl, body) {
  try {
    const reader = body.getReader();
    for (;;) {
      const step = await reader.read();
      if (step.done) break;
      dl.buf.push(step.value);
      dl.bufLen += step.value.length;
      wake(dl);
    }
  } catch (err) {
    dl.error = err;
  } finally {
    dl.done = true;
    wake(dl);
  }
}

// Serve [span.start, span.end] (or the whole file when span is null) from a
// live download, buffering the same bytes into the cache blob.
function streamed(dl, span, headers) {
  let pos = span ? span.start : 0;
  const limit = span ? span.end + 1 : Infinity;
  const stream = new ReadableStream({
    async pull(controller) {
      for (;;) {
        if (pos >= limit || (dl.done && dl.bufStart + dl.bufLen <= pos)) {
          if (dl.error) controller.error(dl.error);
          else controller.close();
          return;
        }
        if (dl.bufStart + dl.bufLen > pos) {
          const chunk = take(dl, pos, limit);
          pos += chunk.length;
          controller.enqueue(chunk);
          return;
        }
        await dl.wait;
      }
    },
    cancel() {
      // The download continues so the file still lands in the cache.
    }
  });
  const head = {
    "Content-Type": dl.type || "application/octet-stream",
    "Accept-Ranges": "bytes"
  };
  if (span) {
    head["Content-Range"] = "bytes " + span.start + "-" + span.end + "/" + dl.total;
    head["Content-Length"] = String(span.end - span.start + 1);
    return new Response(stream, { status: 206, headers: head });
  }
  if (dl.total > 0) head["Content-Length"] = String(dl.total);
  return new Response(stream, { status: 200, headers: head });
}

// One download record serves every in-flight consumer: its buffer feeds
// live range streams and finally becomes the cached blob.
function startDownload(cache, url, parts) {
  const dl = {
    buf: [],
    bufLen: 0,
    bufStart: 0,
    done: false,
    error: null,
    total: 0,
    type: "",
    waiters: [],
    ready: null,
    blob: null
  };
  Object.defineProperty(dl, "wait", {
    get: function () {
      return new Promise(function (resolve) {
        dl.waiters.push(resolve);
      });
    }
  });
  // ready resolves as soon as the upstream response headers arrive, so a
  // range response can start streaming long before the file completes.
  dl.ready = fetch(url, { mode: "cors", credentials: "omit" }).then(function (res) {
    if (!res.ok) throw new Error("media status " + res.status);
    dl.total = Number(res.headers.get("Content-Length")) || 0;
    dl.type = res.headers.get("Content-Type") || "";
    if (!res.body) throw new Error("no body");
    return res;
  });
  dl.blob = dl.ready
    .then(function (res) {
      return pump(dl, res.body).then(function () {
        if (dl.error) throw dl.error;
        return new Blob(dl.buf, { type: dl.type || "application/octet-stream" });
      });
    })
    .then(function (blob) {
      return putBlob(cache, url, parts, blob).then(function () {
        return blob;
      });
    });
  dl.blob.then(
    function () {
      pending.delete(url);
    },
    function () {
      pending.delete(url);
    }
  );
  pending.set(url, dl);
  return dl;
}

async function serve(cache, request, url) {
  const rangeHeader = request.headers.get("range");
  const parts = mediaParts(url);
  const hit = await cache.match(url).catch(function () {
    return null;
  });
  if (hit) {
    touch(cache, url, parts);
    const blob = await hit.blob();
    return rangeHeader ? ranged(blob, parseRange(rangeHeader, blob.size)) : new Response(blob);
  }
  const dl = pending.get(url) || startDownload(cache, url, parts);
  const up = await dl.ready.then(
    function () {
      return true;
    },
    function () {
      return false;
    }
  );
  if (!up || (dl.done && dl.error)) return fetch(request);
  if (!rangeHeader) {
    // Streaming pass-through on a miss keeps first-play latency unchanged;
    // the same bytes are buffered for the cache write.
    return streamed(dl, null);
  }
  if (!dl.total) {
    // No Content-Length: answer the range from the finished blob instead.
    const blob = await dl.blob.catch(function () {
      return null;
    });
    if (!blob) return fetch(request);
    return ranged(blob, parseRange(rangeHeader, blob.size));
  }
  const range = parseRange(rangeHeader, dl.total);
  if (!range) return streamed(dl, null); // malformed range: serve the body
  if (range.start >= dl.total || range.end < range.start) {
    return new Response(null, {
      status: 416,
      headers: { "Content-Range": "bytes */" + dl.total }
    });
  }
  const span = { start: range.start, end: Math.min(range.end, dl.total - 1) };
  if (dl.done) {
    const blob = await dl.blob.catch(function () {
      return null;
    });
    if (!blob) return fetch(request);
    return ranged(blob, span);
  }
  return streamed(dl, span);
}

async function prefetch(urls) {
  const cache = await caches.open(CACHE);
  const jobs = [];
  for (const raw of urls || []) {
    const url = String(raw || "");
    if (!url || !hasRev(url)) continue;
    try {
      if (new URL(url).origin !== self.location.origin) continue;
      if (!isMediaPath(new URL(url).pathname)) continue;
    } catch (err) {
      continue;
    }
    const hit = await cache.match(url).catch(function () {
      return null;
    });
    if (hit || pending.has(url)) continue;
    const parts = mediaParts(url);
    const dl = startDownload(cache, url, parts);
    jobs.push(dl.blob.catch(function () {}));
  }
  await Promise.all(jobs);
}

async function stats() {
  const cache = await caches.open(CACHE);
  const index = await loadIndex(cache);
  let songs = 0;
  let size = 0;
  for (const song in index) {
    const entry = index[song];
    if (!entry || !entry.files) continue;
    songs += 1;
    size += entry.size || 0;
  }
  return { songs: songs, bytes: size, budget: BUDGET };
}

self.addEventListener("install", function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function (event) {
  const request = event.request;
  if (request.method !== "GET") return;
  let url;
  try {
    url = new URL(request.url);
  } catch (err) {
    return;
  }
  if (url.origin !== self.location.origin || !isMediaPath(url.pathname)) return;
  if (!hasRev(request.url)) return; // unversioned media may still change
  event.respondWith(
    caches
      .open(CACHE)
      .then(function (cache) {
        return serve(cache, request, request.url);
      })
      .catch(function () {
        return fetch(request);
      })
  );
});

self.addEventListener("message", function (event) {
  const data = event.data || {};
  const reply = event.ports && event.ports[0];
  if (data.type === "lovktv-media-prefetch") {
    event.waitUntil(prefetch(data.urls));
  } else if (data.type === "lovktv-media-clear") {
    event.waitUntil(
      caches.delete(CACHE).then(function () {
        indexPromise = null;
        if (reply) reply.postMessage({ ok: true });
      })
    );
  } else if (data.type === "lovktv-media-stats") {
    event.waitUntil(
      stats().then(function (result) {
        if (reply) reply.postMessage(result);
      })
    );
  }
});
