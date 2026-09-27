import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { celebrateCorrect, onPress, playMissSfx, playSelectSfx } from "./fx.js";
import { cancelCueWindow, paintLearnLine, playCueWindow } from "./play.js";

/**
 * A missed item comes back at the end of the run, up to this many extra times,
 * so the learner leaves having answered it right at least once. Only the first
 * try is scored and saved; the mistake book owns the long-term review.
 */
const MAX_REDRILL = 2;

/** @type {{ lesson: any, queue: any[], index: number, answers: Map<string, any>, tries: Map<string, number>, cleared: Set<string>, gen: number, locked: boolean, running: boolean, missed: boolean, streak: number, best: number, matchLeft: number | null, matched: Set<number>, matchMisses: number, done: ((score: any) => void) | null }} */
const session = {
  lesson: null,
  queue: [],
  index: 0,
  answers: new Map(),
  tries: new Map(),
  cleared: new Set(),
  gen: 0,
  locked: false,
  running: false,
  missed: false,
  streak: 0,
  best: 0,
  matchLeft: null,
  matched: new Set(),
  matchMisses: 0,
  done: null
};

export function stopLesson() {
  session.gen += 1;
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
  return session.queue[session.index];
}

function paintBar() {
  const total = items().length;
  const bar = $("learnLessonBar");
  // The bar counts items answered right, so a miss leaves a gap until it is fixed.
  if (bar) bar.style.width = `${Math.round((session.cleared.size / (total || 1)) * 100)}%`;
  const combo = $("learnLessonCombo");
  if (!combo) return;
  if (!total) {
    combo.textContent = "";
    return;
  }
  const head =
    session.index < total
      ? `${session.index + 1} / ${total}`
      : t("learn.lesson.redrill", { n: session.queue.length - session.index });
  combo.textContent = session.streak > 1 ? `${head} · ${t("learn.feedback.streak", { n: session.streak })}` : head;
}

function paintFeedback(message, isNo = false) {
  const el = $("learnLessonFeedback");
  if (!el) return;
  el.hidden = !message;
  el.classList.toggle("is-no", !!isNo);
  el.textContent = message || "";
  // Restart the entrance animation when feedback changes between items.
  if (message) {
    el.style.animation = "none";
    void el.offsetWidth;
    el.style.animation = "";
  }
}

function hasWindow(item) {
  return !!item && item.start_ms != null && item.end_ms != null;
}

function playItem(item) {
  if (hasWindow(item)) playCueWindow(item.start_ms, item.end_ms, { vocal: true });
}

function lineBox() {
  const src = $("learnLessonSrc");
  return src ? src.closest(".learn-line") : null;
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
  const box = lineBox();
  if (box) box.classList.remove("is-reveal");
  const prompt = $("learnLessonPrompt");
  if (prompt) {
    prompt.textContent = (item && item.prompt) || "";
    prompt.hidden = !prompt.textContent;
  }
  const replay = $("learnLessonReplay");
  if (replay) replay.hidden = !(item && item.kind === "listen");
}

/**
 * After a miss, show the whole lyric line with its translation and replay it,
 * so the answer is learned in context instead of only being marked.
 */
function revealLine(item) {
  const lines = (session.lesson && session.lesson.lines) || [];
  const line = item.line_index != null ? lines.find((row) => row.index === item.line_index) : null;
  const word = item.knowledge && item.knowledge.kind === "word" ? item.knowledge.text : "";
  // Word drills fall back to the unit's first line when the token has no host line.
  if (line && line.text && (!word || line.text.includes(word))) {
    paintLearnLine({
      src: "learnLessonSrc",
      roma: "learnLessonRoma",
      zh: "learnLessonZh",
      text: line.text,
      romaji: line.romaji,
      zhText: line.zh || item.translation,
      hideZh: false
    });
    const box = lineBox();
    if (box) box.classList.add("is-reveal");
  }
  if (!hasWindow(item)) return;
  const replay = $("learnLessonReplay");
  if (replay) replay.hidden = false;
  playItem(item);
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

function choiceButtons(item) {
  // A redrilled item reshuffles so the answer is recalled, not found by position.
  const choices = session.tries.has(item.id) ? shuffle(item.choices || []) : item.choices || [];
  return `
    <div class="learn-choices">
      ${choices
        .map(
          (choice) =>
            `<button type="button" class="learn-choice" data-cid="${choice.id}">${escapeHtml(choice.text)}</button>`
        )
        .join("")}
    </div>
  `;
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
  paintFeedback("");
  paintBar();
  if (!item || !box) {
    if (box) box.innerHTML = "";
    return;
  }
  showStem(item);
  if (item.kind === "match") box.innerHTML = matchButtons(item);
  else box.innerHTML = choiceButtons(item);
  box.querySelectorAll(".learn-choice").forEach((btn) => {
    onPress(btn, () => pickChoice(Number(btn.dataset.cid), btn));
  });
  box.querySelectorAll(".learn-match-btn").forEach((btn) => {
    onPress(btn, () => pickMatch(btn));
  });
  // A match board has no line of its own; stop whatever the last item played.
  if (hasWindow(item)) playItem(item);
  else cancelCueWindow();
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

/** @returns {boolean} whether the item was queued for another try */
function requeue(item) {
  const tries = (session.tries.get(item.id) || 0) + 1;
  session.tries.set(item.id, tries);
  if (tries > MAX_REDRILL) return false;
  session.queue.push(item);
  return true;
}

/** Advance after `ms` unless the lesson moved on or was stopped meanwhile. */
function advanceLater(ms) {
  const gen = session.gen;
  const at = session.index;
  window.setTimeout(() => {
    if (session.gen === gen && session.index === at) advance();
  }, ms);
}

/** Listen drills and the romaji lyric mode hide the source line; burst from the choices instead. */
function burstAnchor() {
  const src = $("learnLessonSrc");
  return src && src.getClientRects().length ? src : $("learnLessonQs");
}

function finishItem(ok, extra) {
  const item = current();
  if (!item || session.locked) return;
  session.locked = true;
  const retry = session.tries.has(item.id);
  if (!session.answers.has(item.id)) {
    session.answers.set(
      item.id,
      answerPayload(item, ok, {
        ...(extra || {}),
        matchedIds: Array.from(session.matched),
        matchMisses: session.matchMisses
      })
    );
  }
  session.streak = ok ? session.streak + 1 : 0;
  session.best = Math.max(session.best, session.streak);
  if (ok) session.cleared.add(item.id);
  const again = !ok && requeue(item);
  paintBar();
  if (ok) {
    paintFeedback(
      retry
        ? t("learn.feedback.fixed")
        : session.streak > 1
          ? t("learn.feedback.combo", { n: session.streak })
          : t("learn.feedback.correct")
    );
    celebrateCorrect(burstAnchor(), { line: true, combo: session.streak });
    advanceLater(700);
    return;
  }
  paintFeedback(again ? t("learn.feedback.later") : t("learn.feedback.wrong"), true);
  revealLine(item);
  const next = $("learnLessonNext");
  if (next) {
    next.hidden = false;
    next.textContent = t("learn.continue");
  } else {
    advanceLater(900);
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
    if (session.matchLeft === pid) return;
    $("learnLessonQs")
      .querySelectorAll('[data-side="left"]')
      .forEach((node) => node.classList.toggle("is-on", node === btn));
    session.matchLeft = pid;
    playSelectSfx();
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
  paintFeedback(t("learn.feedback.tryAgain"), true);
  btn.classList.add("is-no");
  window.setTimeout(() => btn.classList.remove("is-no"), 420);
}

function wrapUp() {
  const total = items().length;
  const answers = Array.from(session.answers.values());
  const ok = answers.filter((answer) => answer.ok).length;
  const pct = total ? Math.round((100 * ok) / total) : 0;
  const score = {
    pct,
    ok,
    total,
    // Missed on the first try but answered right on a redrill.
    fixed: answers.filter((answer) => !answer.ok && session.cleared.has(answer.id)).length,
    best: session.best,
    answers,
    review: !!(session.lesson && session.lesson.review)
  };
  session.running = false;
  const done = session.done;
  session.done = null;
  if (done) done(score);
}

function advance() {
  if (!session.running) return;
  if (session.index + 1 >= session.queue.length) {
    const bar = $("learnLessonBar");
    if (bar) bar.style.width = "100%";
    wrapUp();
    return;
  }
  session.index += 1;
  paintItem();
}

export function startLesson(lesson) {
  session.gen += 1;
  session.lesson = lesson;
  session.queue = items().slice();
  session.index = 0;
  session.answers = new Map();
  session.tries = new Map();
  session.cleared = new Set();
  session.streak = 0;
  session.best = 0;
  session.running = false;
  session.locked = false;
  session.done = null;
  $("learnTitle").textContent = lesson && lesson.review ? t("learn.book") : t("learn.lesson");
  $("learnMeta").textContent = (lesson && lesson.title) || "";
  paintItem();
}

export function runLesson() {
  session.running = true;
  return new Promise((resolve) => {
    session.done = resolve;
  });
}

/** @param {any} score @param {(pct: number) => string} grade @returns {LearnScoreView} */
export function lessonScoreView(score, grade) {
  const ok = score.ok || 0;
  const total = score.total || 0;
  const stats = [{ label: t("learn.stat.firstTry"), value: `${ok}/${total}` }];
  if ((score.best || 0) > 1) stats.push({ label: t("learn.stat.best"), value: String(score.best) });
  if (score.fixed) stats.push({ label: t("learn.stat.fixed"), value: String(score.fixed) });
  return {
    title: score.review ? t("learn.score.review") : t("learn.score.lesson"),
    again: t("learn.again.lesson"),
    sub: grade(score.pct || 0),
    detail:
      total && ok >= total
        ? t("learn.score.perfect")
        : score.review
          ? t("learn.bookHint")
          : t("learn.score.lessonHint"),
    mixUrl: "",
    celebrate: (score.pct || 0) >= 70,
    stats
  };
}

export function bindLesson() {
  const next = $("learnLessonNext");
  if (next) next.onclick = () => advance();
  const replay = $("learnLessonReplay");
  if (replay) replay.onclick = () => playItem(current());
}
