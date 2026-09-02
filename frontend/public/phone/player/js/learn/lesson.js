import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { celebrateCorrect, playMissSfx } from "./fx.js";
import { cancelCueWindow, paintLearnLine, playCueWindow } from "./play.js";

/** @type {{ lesson: any, index: number, answers: any[], locked: boolean, running: boolean, missed: boolean, matchLeft: number | null, matched: Set<number>, matchMisses: number, done: ((score: any) => void) | null }} */
const session = {
  lesson: null,
  index: 0,
  answers: [],
  locked: false,
  running: false,
  missed: false,
  matchLeft: null,
  matched: new Set(),
  matchMisses: 0,
  done: null
};

export function stopLesson() {
  session.running = false;
  session.locked = false;
  const done = session.done;
  session.done = null;
  if (done) done(null);
  cancelCueWindow();
  const next = $("learnLessonNext");
  if (next) next.hidden = true;
}

export function lessonBusy() {
  return session.running;
}

function items() {
  return (session.lesson && session.lesson.items) || [];
}

function current() {
  return items()[session.index];
}

function paintBar() {
  const bar = $("learnLessonBar");
  const total = items().length || 1;
  if (bar) bar.style.width = `${Math.round((session.index / total) * 100)}%`;
  const combo = $("learnLessonCombo");
  if (combo) combo.textContent = items().length ? `${session.index + 1} / ${items().length}` : "";
}

function playItem(item) {
  if (!item) return;
  if (item.kind === "listen" || item.start_ms != null) {
    if (item.start_ms != null && item.end_ms != null) {
      playCueWindow(item.start_ms, item.end_ms, { vocal: true });
    }
  }
}

function showStem(item) {
  const listen = item && item.kind === "listen";
  const hideSrc = listen && !item.stem;
  paintLearnLine({
    src: "learnLessonSrc",
    roma: "learnLessonRoma",
    zh: "learnLessonZh",
    text: hideSrc ? "" : (item && item.stem) || "",
    romaji: hideSrc ? "" : (item && item.romaji) || "",
    zhText: "",
    hideSrc,
    hideZh: true
  });
  const prompt = $("learnLessonPrompt");
  if (prompt) {
    prompt.textContent = (item && item.prompt) || "";
    prompt.hidden = !prompt.textContent;
  }
  const replay = $("learnLessonReplay");
  if (replay) replay.hidden = !(item && item.kind === "listen");
}

function choiceButtons(item) {
  return `
    <div class="learn-choices">
      ${(item.choices || [])
        .map(
          (choice) =>
            `<button type="button" class="learn-choice" data-cid="${choice.id}">${escapeHtml(choice.text)}</button>`
        )
        .join("")}
    </div>
  `;
}

function shuffle(list) {
  const copy = list.slice();
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = copy[i];
    copy[i] = copy[j];
    copy[j] = tmp;
  }
  return copy;
}

function matchButtons(item) {
  const pairs = item.pairs || [];
  const rights = shuffle(pairs.map((pair) => ({ id: pair.id, text: pair.right })));
  return `
    <div class="learn-match">
      <div class="learn-match-col">
        ${pairs
          .map(
            (pair) =>
              `<button type="button" class="learn-match-btn" data-side="left" data-pid="${pair.id}">${escapeHtml(
                pair.left
              )}</button>`
          )
          .join("")}
      </div>
      <div class="learn-match-col">
        ${rights
          .map(
            (pair) =>
              `<button type="button" class="learn-match-btn" data-side="right" data-pid="${pair.id}">${escapeHtml(
                pair.text
              )}</button>`
          )
          .join("")}
      </div>
    </div>
  `;
}

function paintItem() {
  const item = current();
  const box = $("learnLessonQs");
  const next = $("learnLessonNext");
  if (next) next.hidden = true;
  session.locked = false;
  session.missed = false;
  session.matchLeft = null;
  session.matched = new Set();
  session.matchMisses = 0;
  paintBar();
  if (!item || !box) {
    if (box) box.innerHTML = "";
    return;
  }
  showStem(item);
  if (item.kind === "match") box.innerHTML = matchButtons(item);
  else box.innerHTML = choiceButtons(item);
  box.querySelectorAll(".learn-choice").forEach((btn) => {
    btn.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      pickChoice(Number(btn.dataset.cid), btn);
    });
  });
  box.querySelectorAll(".learn-match-btn").forEach((btn) => {
    btn.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      pickMatch(btn);
    });
  });
  playItem(item);
}

function knowledgeOf(item, extra) {
  const base = Object.assign({}, item && item.knowledge, extra || {});
  return {
    kind: base.kind || (item && item.kind === "word" ? "word" : "sentence"),
    key: base.key || (item && (item.stem || item.answer_text)) || "",
    text: base.text || (item && item.stem) || "",
    zh: base.zh || (item && item.answer_text) || ""
  };
}

function answerPayload(item, ok, extra) {
  return {
    id: item.id,
    ok,
    qkind: item.kind,
    key: (item.knowledge && item.knowledge.key) || item.stem,
    prompt: item.prompt,
    stem: item.stem,
    answer_text: item.answer_text,
    choices: item.choices,
    answer: item.answer,
    pairs: item.pairs,
    blank: item.blank,
    start_ms: item.start_ms,
    end_ms: item.end_ms,
    line_index: item.line_index,
    picked: extra && extra.picked,
    matched_ids: (extra && extra.matchedIds) || [],
    match_misses: (extra && extra.matchMisses) || 0,
    knowledge: knowledgeOf(item, extra)
  };
}

function finishItem(ok, extra) {
  const item = current();
  if (!item || session.locked) return;
  session.locked = true;
  session.answers.push(
    answerPayload(item, ok, {
      ...(extra || {}),
      matchedIds: Array.from(session.matched),
      matchMisses: session.matchMisses
    })
  );
  const next = $("learnLessonNext");
  if (ok) {
    celebrateCorrect($("learnLessonSrc") || $("learnLessonPrompt"), { line: true });
    window.setTimeout(() => advance(), 700);
  } else if (next) {
    next.hidden = false;
    next.textContent = t("learn.continue");
  } else {
    window.setTimeout(() => advance(), 900);
  }
}

function pickChoice(cid, btn) {
  const item = current();
  if (!item || session.locked) return;
  const ok = cid === item.answer;
  $("learnLessonQs")
    .querySelectorAll(".learn-choice")
    .forEach((node) => {
      const id = Number(node.dataset.cid);
      node.disabled = true;
      node.classList.toggle("is-ok", id === item.answer);
      node.classList.toggle("is-no", node === btn && !ok);
    });
  if (!ok) playMissSfx();
  finishItem(ok, { picked: cid });
}

function markPair(pid, ok) {
  $("learnLessonQs")
    .querySelectorAll(`[data-pid="${pid}"]`)
    .forEach((node) => {
      node.classList.toggle("is-ok", ok);
      node.classList.toggle("is-on", false);
      if (ok) node.disabled = true;
    });
}

function pickMatch(btn) {
  const item = current();
  if (!item || session.locked || btn.disabled) return;
  const pid = Number(btn.dataset.pid);
  const side = btn.dataset.side;
  if (session.matched.has(pid) && side) return;
  if (side === "left") {
    $("learnLessonQs")
      .querySelectorAll('[data-side="left"]')
      .forEach((node) => node.classList.toggle("is-on", node === btn));
    session.matchLeft = pid;
    return;
  }
  if (session.matchLeft == null) return;
  const left = session.matchLeft;
  session.matchLeft = null;
  $("learnLessonQs")
    .querySelectorAll(".learn-match-btn")
    .forEach((node) => node.classList.remove("is-on"));
  if (left === pid) {
    session.matched.add(pid);
    markPair(pid, true);
    if (session.matched.size >= (item.pairs || []).length) finishItem(!session.missed);
    return;
  }
  session.missed = true;
  session.matchMisses += 1;
  playMissSfx();
  btn.classList.add("is-no");
  window.setTimeout(() => btn.classList.remove("is-no"), 420);
}

function wrapUp() {
  const total = items().length;
  const ok = session.answers.filter((item) => item.ok).length;
  const pct = total ? Math.round((100 * ok) / total) : 0;
  const score = { pct, ok, total, answers: session.answers, review: !!(session.lesson && session.lesson.review) };
  session.running = false;
  if (session.done) session.done(score);
}

function advance() {
  if (!session.running) return;
  if (session.index + 1 >= items().length) {
    const bar = $("learnLessonBar");
    if (bar) bar.style.width = "100%";
    wrapUp();
    return;
  }
  session.index += 1;
  paintItem();
}

export function startLesson(lesson) {
  session.lesson = lesson;
  session.index = 0;
  session.answers = [];
  session.running = false;
  session.locked = false;
  session.done = null;
  $("learnTitle").textContent = lesson && lesson.review ? t("learn.book") : t("learn.lesson");
  $("learnMeta").textContent = (lesson && lesson.title) || "";
  paintItem();
}

export function runLesson() {
  session.running = true;
  paintItem();
  return new Promise((resolve) => {
    session.done = resolve;
  });
}

/** @param {any} score @param {(pct: number) => string} grade @returns {LearnScoreView} */
export function lessonScoreView(score, grade) {
  return {
    title: t("learn.score.lesson"),
    again: t("learn.again.lesson"),
    sub: `${grade(score.pct)} · ${score.ok || 0}/${score.total || 0}`,
    detail: t("learn.score.lessonHint"),
    mixUrl: "",
    celebrate: (score.pct || 0) >= 70
  };
}

export function bindLesson() {
  const next = $("learnLessonNext");
  if (next) next.onclick = () => advance();
  const replay = $("learnLessonReplay");
  if (replay) replay.onclick = () => playItem(current());
}
