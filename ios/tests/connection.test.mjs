import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { connection, allowedPath } from "../web/policy.js";

async function setup() {
  const nodes = new Map();
  const storage = new Map();
  const configured = [];
  const node = (id) => {
    if (!nodes.has(id))
      nodes.set(id, {
        value: "",
        hidden: false,
        textContent: "",
        children: [],
        replaceChildren() {},
        setAttribute() {},
      });
    return nodes.get(id);
  };
  let responseStatus = 200;
  const native = {
    configure: async (data) => configured.push(data),
    request: async () => ({
      status: responseStatus,
      body: JSON.stringify({ queue: [], songs: [], total: 0 }),
    }),
    stop: async () => {},
  };
  const source = await readFile(
    new URL("../web/app.js", import.meta.url),
    "utf8",
  );
  const context = vm.createContext({
    connection,
    allowedPath,
    window: { Capacitor: { registerPlugin: () => native } },
    document: {
      getElementById: node,
      querySelectorAll: () => [],
      addEventListener() {},
    },
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    setInterval() {},
    console,
  });
  vm.runInContext(source.replace(/^import .*;\n/, ""), context);
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  return {
    node,
    storage,
    configured,
    settle,
    fail: () => {
      responseStatus = 401;
    },
  };
}

test("official credentials cross bridge but never enter web storage; forget clears native storage", async () => {
  const app = await setup();
  app.node("mode").value = "official";
  app.node("room").value = "ABCD";
  app.node("api-key").value = "lkr_test-secret";
  app.node("connect").onsubmit({ preventDefault() {} });
  await app.settle();
  assert.equal(app.configured[0].apiKey, "lkr_test-secret");
  assert.equal(app.configured[0].server, "https://ktv.lovbrowser.com");
  assert.equal(app.configured[0].official, true);
  assert.equal(app.node("api-key").value, "");
  assert(!JSON.stringify([...app.storage]).includes("lkr_test-secret"));
  assert.equal(JSON.parse(app.storage.get("remote-config")).mode, "official");
  app.fail();
  app.node("search").onsubmit({ preventDefault() {} });
  await app.settle();
  assert.equal(app.node("status").textContent, "API key 无效或已失效");
  app.node("forget").onclick();
  await app.settle();
  assert.equal(app.configured.at(-1).server, "");
  assert.equal(app.storage.size, 0);
});

test("self-hosted mode retains its server and does not receive an official key", async () => {
  const app = await setup();
  app.node("mode").value = "self";
  app.node("server").value = "http://192.168.1.4:8790";
  app.node("room").value = "ABCD";
  app.node("connect").onsubmit({ preventDefault() {} });
  await app.settle();
  assert.equal(app.configured[0].official, false);
  assert.equal(app.configured[0].apiKey, "");
  assert.equal(app.configured[0].server, "http://192.168.1.4:8790");
  assert.equal(app.node("status").textContent, "已连接自己的服务器");
});
