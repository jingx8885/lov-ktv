import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

function element(line) {
  const classes = new Set();
  const el = {
    hidden: false,
    disabled: false,
    dataset: {},
    children: [],
    textContent: "",
    style: {},
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name))
    },
    closest: () => line,
    getClientRects: () => [{}],
    querySelectorAll(selector) {
      const attr = /^\[data-(\w+)="([^"]*)"\]$/.exec(selector);
      return this.children.filter((child) =>
        attr ? child.dataset[attr[1]] === attr[2] : child.classList.contains(selector.slice(1))
      );
    }
  };
  // Lesson items render their buttons as markup; keep just the buttons, flattened.
  Object.defineProperty(el, "innerHTML", {
    set(html) {
      this.children = Array.from(String(html).matchAll(/<button ([^>]*)>([^<]*)<\/button>/g), ([, attrs, text]) => {
        const btn = element(line);
        btn.textContent = text;
        for (const [, name, value] of attrs.matchAll(/data-(\w+)="([^"]*)"/g)) btn.dataset[name] = value;
        /class="([^"]*)"/
          .exec(attrs)[1]
          .split(/\s+/)
          .forEach((name) => btn.classList.add(name));
        return btn;
      });
    }
  });
  return el;
}

async function harness(lesson) {
  const line = element(null);
  const nodes = new Map();
  const $ = (id) => {
    if (!nodes.has(id)) nodes.set(id, element(line));
    return nodes.get(id);
  };
  const timers = [];
  const painted = [];
  const dependencies = {
    $,
    escapeHtml: (text) => String(text),
    t: (key, vars) => (vars ? `${key} ${JSON.stringify(vars)}` : key),
    celebrateCorrect() {},
    onPress(btn, fn) {
      btn.press = fn;
    },
    playMissSfx() {},
    playSelectSfx() {},
    cancelCueWindow() {},
    paintLearnLine(opts) {
      painted.push(opts);
    },
    playCueWindow: () => Promise.resolve(true)
  };
  const context = vm.createContext({ window: { setTimeout: (fn) => timers.push(fn) } });
  const source = await readFile(new URL("../public/phone/player/js/learn/lesson.js", import.meta.url), "utf8");
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
  // Arrays built inside the context have that realm's prototype, so assertions copy them out with Array.from.
  const api = module.namespace;
  api.bindLesson();
  api.startLesson(lesson);
  const result = api.runLesson();
  return {
    $,
    api,
    line,
    painted,
    result,
    feedback: () => $("learnLessonFeedback").textContent,
    pick(text) {
      $("learnLessonQs")
        .children.find((btn) => btn.textContent === text)
        .press();
    },
    next() {
      $("learnLessonNext").onclick();
    },
    flush() {
      while (timers.length) timers.shift()();
    }
  };
}

const item = (id) => ({
  id,
  kind: "word",
  prompt: "pick",
  stem: id,
  choices: [
    { id: 0, text: `${id}:right` },
    { id: 1, text: `${id}:wrong` }
  ],
  answer: 0,
  answer_text: `${id}:right`,
  start_ms: 1000,
  end_ms: 2000,
  line_index: 0
});
const lesson = (ids) => ({
  title: "Song",
  items: ids.map(item),
  lines: [{ index: 0, text: ids.join(" "), zh: "中文" }]
});

test("a miss comes back at the end of the run, but only the first try is scored", async () => {
  const h = await harness(lesson(["a", "b", "c"]));
  h.pick("a:wrong");
  assert.equal(h.feedback(), "learn.feedback.later");
  assert.equal(h.$("learnLessonNext").hidden, false);
  // The miss reveals the whole line with its translation.
  assert.equal(h.line.classList.contains("is-reveal"), true);
  assert.equal(h.painted.at(-1).zhText, "中文");
  h.next();
  assert.equal(h.line.classList.contains("is-reveal"), false);
  h.pick("b:right");
  h.flush();
  h.pick("c:right");
  h.flush();
  assert.match(h.$("learnLessonCombo").textContent, /^learn\.lesson\.redrill \{"n":1\}/);
  h.pick("a:right");
  assert.equal(h.feedback(), "learn.feedback.fixed");
  h.flush();
  const score = await h.result;
  assert.deepEqual(
    Array.from(score.answers, (answer) => [answer.id, answer.ok]),
    [
      ["a", false],
      ["b", true],
      ["c", true]
    ]
  );
  assert.equal(score.ok, 2);
  assert.equal(score.total, 3);
  assert.equal(score.pct, 67);
  assert.equal(score.fixed, 1);
  assert.equal(score.best, 3);
});

test("an item missed every time stops coming back after two redrills", async () => {
  const h = await harness(lesson(["a"]));
  h.pick("a:wrong");
  h.next();
  h.pick("a:wrong");
  assert.equal(h.feedback(), "learn.feedback.later");
  h.next();
  h.pick("a:wrong");
  assert.equal(h.feedback(), "learn.feedback.wrong");
  h.next();
  const score = await h.result;
  assert.equal(score.answers.length, 1);
  assert.equal(score.ok, 0);
  assert.equal(score.fixed, 0);
});

test("stopping mid-run resolves with no score and drops the pending advance", async () => {
  const h = await harness(lesson(["a", "b"]));
  h.pick("a:right");
  h.api.stopLesson();
  h.flush();
  assert.equal(await h.result, null);
  assert.equal(h.api.lessonBusy(), false);
});

test("the score view counts first tries and calls out a perfect run", async () => {
  const h = await harness(lesson(["a"]));
  const grade = () => "grade";
  const perfect = h.api.lessonScoreView({ pct: 100, ok: 3, total: 3, best: 3, fixed: 0 }, grade);
  assert.equal(perfect.detail, "learn.score.perfect");
  assert.deepEqual(
    Array.from(perfect.stats, (stat) => [stat.label, stat.value]),
    [
      ["learn.stat.firstTry", "3/3"],
      ["learn.stat.best", "3"]
    ]
  );
  const missed = h.api.lessonScoreView({ pct: 67, ok: 2, total: 3, best: 1, fixed: 1 }, grade);
  assert.equal(missed.detail, "learn.score.lessonHint");
  assert.deepEqual(
    Array.from(missed.stats, (stat) => stat.label),
    ["learn.stat.firstTry", "learn.stat.fixed"]
  );
});
