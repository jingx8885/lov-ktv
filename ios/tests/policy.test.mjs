import { test } from "node:test";
import assert from "node:assert/strict";
import { connection, allowedPath } from "../web/policy.js";
test("manual and TV QR configuration; private HTTP only", () => {
  assert.deepEqual(connection("http://192.168.1.4:8790/m.html?room=ABCD12"), {
    server: "http://192.168.1.4:8790",
    room: "ABCD12",
  });
  assert.equal(connection("https://own.example", "abcd").room, "ABCD");
  for (const url of [
    "http://public.example",
    "javascript:alert(1)",
    "https://user:pass@own.example",
    "https://own.example/billing.html",
    "http://172.32.1.2",
  ])
    assert.throws(() => connection(url, "ABCD"));
});
test("API boundary excludes search providers, accounts, payment, ads and uploads", () => {
  assert(allowedPath("/api/songs?q=abc&page=1", "GET"));
  assert(allowedPath("/api/rooms/ABCD12/queue", "POST"));
  assert(allowedPath("/api/remote/reports", "POST"));
  for (const path of [
    "/api/search?q=abc",
    "/api/auth/register",
    "/api/billing/checkout",
    "/api/ads",
    "/api/songs/import",
    "//evil.test/api/songs",
    "/api/lyric_candidates",
    "/api/apps",
  ])
    for (const method of ["GET", "POST"])
      assert.equal(allowedPath(path, method), false);
});

test("packaged bundle has no remote HTML, providers or monetization assets", async () => {
  const { readdir, readFile } = await import("node:fs/promises");
  const files = await readdir(new URL("../www/", import.meta.url));
  assert.deepEqual(files.sort(), [
    "app.js",
    "capacitor-runtime.js",
    "icon.png",
    "index.html",
    "policy.js",
    "style.css",
  ]);
  const config = JSON.parse(
    await readFile(
      new URL("../capacitor.config.json", import.meta.url),
      "utf8",
    ),
  );
  assert.equal(config.appId, "com.lovktv.phone");
  assert.equal(config.server, undefined);
  const html = await readFile(
    new URL("../www/index.html", import.meta.url),
    "utf8",
  );
  assert(!/(?:src|href)=["\']https?:\/\//.test(html));
  assert(!/billing|login.html|ads|apk|youtube|netease|bilibili/i.test(html));
});

test("official mode has input-only credentials and native Keychain isolation", async () => {
  const { readFile } = await import("node:fs/promises");
  const app = await readFile(new URL("../web/app.js", import.meta.url), "utf8");
  const html = await readFile(
    new URL("../web/index.html", import.meta.url),
    "utf8",
  );
  const native = await readFile(
    new URL("../ios/App/App/RemotePlugin.swift", import.meta.url),
    "utf8",
  );
  assert.match(html, /官方服务/);
  assert.match(html, /id="api-key"\s+type="password"/);
  assert(!/购买|开通会员|价格|申请.*key|billing\.html/i.test(html));
  assert.match(app, /API key 无效或已失效/);
  assert(!/localStorage\.setItem\([^\n]*(?:apiKey|api-key)/.test(app));
  assert.match(native, /SecItemCopyMatching/);
  assert.match(native, /SecItemUpdate/);
  assert.match(native, /SecItemDelete/);
  assert.match(native, /kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly/);
  assert.match(native, /host == "ktv.lovbrowser.com"/);
  assert.match(native, /if official \{ request.setValue\("Bearer "/);
  assert.match(native, /completionHandler\(nil\)/);
  assert.match(native, /\/api\/remote\/ios\/media\//);
});
