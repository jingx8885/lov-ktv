import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

function element() {
  const classes = new Set();
  const el = {
    hidden: false,
    disabled: false,
    dataset: {},
    children: [],
    textContent: "",
    style: { setProperty() {} },
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name)
    },
    setAttribute() {},
    addEventListener(name, fn) {
      this[name] = fn;
    },
    appendChild(child) {
      this.children.push(child);
    },
    querySelectorAll(selector) {
      return this.children.filter((child) => !selector.includes(":not") || !child.classList.contains("is-hit"));
    }
  };
  Object.defineProperty(el, "innerHTML", {
    set() {
      this.children = [];
    }
  });
  return el;
}

async function harness(lines) {
  const nodes = new Map();
  const $ = (id) => {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  };
  let cueDone = null;
  let holdDone = null;
  const starts = [];
  const frames = new Map();
  let frameId = 0;
  const confirmLineHold = () => {
    if (!holdDone) return false;
    const done = holdDone;
    holdDone = null;
    $("learnTapNext").hidden = true;
    done(true);
    return true;
  };
  const dependencies = {
    $,
    escapeHtml: (text) => String(text),
    t: (key) => key,
    state: {},
    showToast() {},
    hookPlayerAudio() {},
    celebrateCorrect() {},
    playMissSfx() {},
    cancelCueWindow() {
      const done = cueDone;
      cueDone = null;
      done?.(false);
    },
    cancelLineHold() {
      const done = holdDone;
      holdDone = null;
      done?.(false);
    },
    confirmLineHold,
    holdAfterLine({ button }) {
      button.hidden = false;
      return new Promise((resolve) => {
        holdDone = resolve;
      });
    },
    isLineHold: () => !!holdDone,
    needsLineHold: () => true,
    paintLearnLine() {},
    playCueWindow(start) {
      starts.push(start);
      return new Promise((resolve) => {
        cueDone = resolve;
      });
    }
  };
  const context = vm.createContext({
    document: { body: { dataset: {} }, createElement: element },
    window: { setTimeout },
    requestAnimationFrame(fn) {
      frames.set(++frameId, fn);
      return frameId;
    },
    cancelAnimationFrame(id) {
      frames.delete(id);
    }
  });
  const source = await readFile(new URL("../public/phone/player/js/learn/tap.js", import.meta.url), "utf8");
  const module = new vm.SourceTextModule(source, { context });
  const stub = new vm.SyntheticModule(
    Object.keys(dependencies),
    function () {
      for (const [name, value] of Object.entries(dependencies)) this.setExport(name, value);
    },
    { context }
  );
  await module.link(() => stub);
  await module.evaluate();
  const api = module.namespace;
  api.bindTap();
  api.startTap({ lines });
  const result = api.runTap();
  const settle = async () => {
    for (let i = 0; i < 6; i++) await Promise.resolve();
  };
  return {
    $,
    api,
    result,
    starts,
    settle,
    tiles: () => $("learnTapField").children,
    tap(i) {
      this.tiles()[i].pointerdown({ preventDefault() {} });
    },
    async next() {
      $("learnTapNext").onclick();
      await settle();
    },
    async endAudio() {
      const done = cueDone;
      cueDone = null;
      done(true);
      await settle();
    },
    async clock(ms) {
      $("playerAudio").currentTime = ms / 1000;
      const pending = Array.from(frames.values());
      frames.clear();
      pending.forEach((fn) => fn());
      await settle();
    }
  };
}
const line = (words, start = 0) => ({ start_ms: start, end_ms: start + 1000, words: words.map((text) => ({ text })) });

test("duplicate tiles can be selected in reverse occurrence order; used tiles cannot score twice", async () => {
  const h = await harness([line(["你", "好", "你"])]);
  h.tap(2);
  h.tap(2);
  assert.equal(h.$("learnTapStrip").children.length, 1);
  h.tap(1);
  h.api.syncTapLyricMode();
  h.tap(0);
  assert.equal(h.$("learnTapNext").hidden, false);
  await h.next();
  const score = await h.result;
  assert.equal(score.hits, 3);
  assert.equal(score.misses, 0);
  assert.equal(score.pct, 100);
});

test("a different word still misses; next works before audio ends and on the final sentence", async () => {
  const h = await harness([line(["你", "好"]), line(["我"], 2000)]);
  h.tap(1);
  assert.equal(h.tiles()[1].classList.contains("is-hit"), false);
  h.tap(0);
  h.tap(1);
  await h.next();
  assert.deepEqual(h.starts, [0, 2000]);
  assert.equal(h.$("learnTapNext").hidden, true);
  h.tap(0);
  await h.next();
  const score = await h.result;
  assert.equal(score.hits, 3);
  assert.equal(score.misses, 1);
  assert.equal(score.total, 2);
});

test("the final sentence remains answerable after playback and finishes through next", async () => {
  const h = await harness([line(["你好"])]);
  await h.endAudio();
  assert.equal(h.api.tapBusy(), true);
  assert.equal(h.$("learnTapNext").hidden, false);
  await h.clock(10000);
  h.tap(0);
  await h.next();
  assert.equal((await h.result).pct, 100);
});

test("replay during playback keeps the session and previously selected words", async () => {
  const h = await harness([line(["你", "好"])]);
  h.tap(0);
  h.api.replayTapLine();
  await h.settle();
  assert.deepEqual(h.starts, [0, 0]);
  assert.equal(h.api.tapBusy(), true);
  assert.equal(h.tiles()[0].classList.contains("is-hit"), true);
  h.tap(1);
  await h.next();
  assert.equal((await h.result).pct, 100);
});

test("skipping the final sentence exits cleanly and counts remaining words", async () => {
  const h = await harness([line(["你", "好"])]);
  h.tap(0);
  h.api.skipTapLine();
  await h.settle();
  const score = await h.result;
  assert.equal(score.hits, 1);
  assert.equal(score.misses, 1);
});
