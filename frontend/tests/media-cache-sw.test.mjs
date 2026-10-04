import assert from "node:assert/strict";
import { test } from "node:test";

// Drive frontend/public/sw-media.js with stubbed service-worker globals so
// the cache, range, and eviction logic can be verified under plain Node.

const SW_PATH = "../public/sw-media.js";

function keyOf(k) {
  return typeof k === "string" ? k : k.url;
}

function fakeCache() {
  const store = new Map();
  return {
    store,
    // CacheStorage hands out a fresh Response per match; mimic that by
    // storing the body once and cloning it on every read.
    async match(k) {
      const entry = store.get(keyOf(k));
      return entry ? new Response(entry.blob, entry.head) : null;
    },
    async put(k, res) {
      const blob = await res.blob();
      const head = blob.type ? { headers: { "Content-Type": blob.type } } : {};
      store.set(keyOf(k), { blob, head });
    },
    async delete(k) {
      return store.delete(keyOf(k));
    },
    async keys() {
      return [...store.keys()].map((u) => new Request(u));
    },
  };
}

const cache = fakeCache();
const network = { calls: [], files: new Map() };

globalThis.self = {
  location: { origin: "https://test.local" },
  LOVKTV_MEDIA_BUDGET: 2000,
  _events: {},
  addEventListener(type, fn) {
    this._events[type] = fn;
  },
  skipWaiting() {
    return Promise.resolve();
  },
  clients: { claim: () => Promise.resolve() },
};

globalThis.caches = {
  async open() {
    return cache;
  },
  async delete() {
    cache.store.clear();
    return true;
  },
};

globalThis.fetch = async (input) => {
  const url = typeof input === "string" ? input : input.url;
  network.calls.push(url);
  const file = network.files.get(url);
  if (!file) return new Response("missing", { status: 404 });
  return new Response(new Blob([file], { type: "audio/mp4" }));
};

await import(SW_PATH);

function media(song, name, rev = "r1") {
  return "https://test.local/media/" + song + "/" + name + "?v=" + rev;
}

function fetchEvent(url, range) {
  const headers = range ? { range } : {};
  const request = new Request(url, { headers });
  const event = {
    request,
    promise: null,
    respondWith(p) {
      this.promise = p;
    },
  };
  self._events.fetch(event);
  return event;
}

function messageEvent(data) {
  const event = {
    data,
    ports: [],
    _p: Promise.resolve(),
    waitUntil(p) {
      this._p = p;
    },
  };
  self._events.message(event);
  return event;
}

async function clearAll() {
  const ev = messageEvent({ type: "lovktv-media-clear" });
  await ev._p;
  cache.store.clear();
}

test("unversioned media and non-media paths bypass the worker", async () => {
  await clearAll();
  const plain = fetchEvent("https://test.local/m.html");
  assert.equal(plain.promise, null);
  const noRev = fetchEvent("https://test.local/media/s1/karaoke.m4a");
  assert.equal(noRev.promise, null);
});

test("first play streams through and lands in the cache", async () => {
  await clearAll();
  const url = media("s1", "karaoke.m4a");
  network.files.set(url, new Uint8Array(400).fill(7));
  const ev = fetchEvent(url);
  const res = await ev.promise;
  assert.equal(res.status, 200);
  const body = await res.arrayBuffer();
  assert.equal(body.byteLength, 400);
  // wait for the background cache write
  await new Promise((r) => setTimeout(r, 30));
  assert.ok(await cache.match(url));
});

test("range request on a miss returns 206 once and caches the whole file", async () => {
  await clearAll();
  const url = media("s2", "original.mp3");
  network.files.set(url, new Uint8Array(300).fill(3));
  const ev = fetchEvent(url, "bytes=10-19");
  const res = await ev.promise;
  assert.equal(res.status, 206);
  assert.equal(res.headers.get("content-range"), "bytes 10-19/300");
  const body = await res.arrayBuffer();
  assert.equal(body.byteLength, 10);
  await new Promise((r) => setTimeout(r, 30));
  assert.equal((await cache.match(url)) && 1, 1);
});

test("replayed track serves ranges from cache without hitting network", async () => {
  const url = media("s2", "original.mp3");
  const before = network.calls.length;
  const ev = fetchEvent(url, "bytes=100-149");
  const res = await ev.promise;
  assert.equal(res.status, 206);
  assert.equal(res.headers.get("content-range"), "bytes 100-149/300");
  const body = new Uint8Array(await res.arrayBuffer());
  assert.equal(body.length, 50);
  assert.equal(body[0], 3);
  assert.equal(network.calls.length, before);
});

test("suffix and out-of-bounds ranges behave like a real file server", async () => {
  const url = media("s2", "original.mp3");
  const suffix = await fetchEvent(url, "bytes=-5").promise;
  assert.equal(suffix.status, 206);
  assert.equal(suffix.headers.get("content-range"), "bytes 295-299/300");
  const over = await fetchEvent(url, "bytes=999-").promise;
  assert.equal(over.status, 416);
  assert.equal(over.headers.get("content-range"), "bytes */300");
});

test("concurrent range requests share one download", async () => {
  await clearAll();
  const url = media("s3", "karaoke.m4a");
  network.files.set(url, new Uint8Array(200).fill(9));
  const a = fetchEvent(url, "bytes=0-9");
  const b = fetchEvent(url, "bytes=50-59");
  const [ra, rb] = await Promise.all([a.promise, b.promise]);
  assert.equal(ra.status, 206);
  assert.equal(rb.status, 206);
  const hits = network.calls.filter((u) => u === url);
  assert.equal(hits.length, 1);
});

test("prefetch message warms files without a page request", async () => {
  await clearAll();
  const url = media("s4", "original.mp3");
  network.files.set(url, new Uint8Array(120).fill(5));
  const ev = messageEvent({ type: "lovktv-media-prefetch", urls: [url] });
  await ev._p;
  await new Promise((r) => setTimeout(r, 30));
  assert.ok(await cache.match(url));
});

test("least recently played song is evicted over budget", async () => {
  await clearAll();
  const one = media("old", "karaoke.m4a");
  const two = media("new", "karaoke.m4a");
  network.files.set(one, new Uint8Array(1200).fill(1));
  network.files.set(two, new Uint8Array(1200).fill(2));
  await (await fetchEvent(one).promise).arrayBuffer();
  await new Promise((r) => setTimeout(r, 40));
  await (await fetchEvent(two).promise).arrayBuffer();
  await new Promise((r) => setTimeout(r, 60));
  assert.equal(await cache.match(one), null);
  assert.ok(await cache.match(two));
});
