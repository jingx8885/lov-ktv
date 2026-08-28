import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { celebrateCorrect, playMissSfx } from "./learn-fx.js";
import { cancelCueWindow, playCueWindow } from "./learn-play.js";

let syncRaf = 0;

/** @type {LearnSession & { running: boolean, combo: number, maxCombo: number, locked: boolean }} */
const session = {
  quiz: null,
  line: 0,
  answers: {},
  running: false,
  combo: 0,
  maxCombo: 0,
  locked: false,
};

/** @param {LearnQuiz} quiz */
export function resetQuiz(quiz) {
  session.quiz = quiz;
  session.line = 0;
  session.answers = {};
  session.running = false;
  session.combo = 0;
  session.maxCombo = 0;
  session.locked = false;
}

export function quizBusy() {
  return session.running;
}

function lines() {
  return (session.quiz && session.quiz.lines) || [];
}

function currentLine() {
  return lines()[session.line];
}

function currentQuestion(line) {
  return line && line.questions && line.questions[0];
}

function lineAt(ms) {
  const list = lines();
  for (let i = 0; i < list.length; i += 1) {
    if (ms >= list[i].start_ms && ms < list[i].end_ms) return i;
  }
  return -1;
}

function paintCombo() {
  const el = $("learnQuizCombo");
  if (!el) return;
  el.textContent = session.running ? `COMBO ${session.combo}` : t("learn.quizLive");
}

function paintMeta() {
  const total = lines().length;
  $("learnTitle").textContent = t("learn.quiz");
  $("learnMeta").textContent = total ? `${session.line + 1} / ${total}` : "";
  paintCombo();
}

function paintClock(ms) {
  const list = lines();
  const bar = $("learnQuizBar");
  if (!bar || !list.length) return;
  const start = list[0].start_ms;
  const end = list[list.length - 1].end_ms;
  const pct = end > start ? Math.max(0, Math.min(1, (ms - start) / (end - start))) : 0;
  bar.style.width = `${Math.round(pct * 100)}%`;
}

function stemRoma(line, item) {
  if (!item || item.kind === "listen") return "";
  if (item.kind === "word") {
    const hit = (line.words || []).find((word) => word.text === item.stem);
    return (hit && hit.romaji) || "";
  }
  return line.romaji || "";
}

/** @param {LearnLine} line */
function paintQuestion(line) {
  const item = currentQuestion(line);
  const listen = !!(item && item.kind === "listen");
  $("learnQuizSrc").textContent = listen ? t("learn.quizListen") : ((item && item.stem) || (line && line.text) || "");
  const roma = $("learnQuizRoma");
  const romaText = listen ? "" : stemRoma(line, item);
  roma.textContent = romaText;
  roma.hidden = !romaText;
  const box = $("learnQuizQs");
  if (!item) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `
    <div class="learn-choices">
      ${(item.choices || []).map((choice) => `
        <button type="button" class="learn-choice" data-cid="${choice.id}">${escapeHtml(choice.text)}</button>
      `).join("")}
    </div>
  `;
  box.querySelectorAll(".learn-choice").forEach((btn) => {
    btn.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      pickChoice(Number(btn.dataset.cid), btn);
    });
  });
  if (session.answers[item.id] != null) markChoices(item, session.answers[item.id]);
}

function markChoices(item, picked) {
  $("learnQuizQs").querySelectorAll(".learn-choice").forEach((btn) => {
    const cid = Number(btn.dataset.cid);
    btn.disabled = true;
    btn.classList.toggle("is-ok", cid === item.answer);
    btn.classList.toggle("is-no", cid === picked && picked !== item.answer);
  });
}

function showLine(index) {
  const line = lines()[index];
  if (!line) return;
  session.line = index;
  const item = currentQuestion(line);
  session.locked = !!(item && session.answers[item.id] != null);
  paintMeta();
  paintQuestion(line);
}

function missQuestion(item) {
  if (!item || session.answers[item.id] != null) return;
  session.answers[item.id] = -1;
  session.combo = 0;
  session.locked = true;
  if (currentQuestion(currentLine()) === item) markChoices(item, -1);
  playMissSfx();
  paintCombo();
}

function flushEnded(ms) {
  lines().forEach((line) => {
    const item = currentQuestion(line);
    if (!item || session.answers[item.id] != null) return;
    if (ms >= line.end_ms) missQuestion(item);
  });
}

function onClock(ms) {
  if (!session.running) return;
  flushEnded(ms);
  const idx = lineAt(ms);
  if (idx >= 0 && idx !== session.line) showLine(idx);
  paintClock(ms);
  paintMeta();
}

function startClock() {
  const audio = $("playerAudio");
  const tick = () => {
    if (!session.running) {
      syncRaf = 0;
      return;
    }
    onClock(((audio && audio.currentTime) || 0) * 1000);
    syncRaf = requestAnimationFrame(tick);
  };
  if (syncRaf) cancelAnimationFrame(syncRaf);
  syncRaf = requestAnimationFrame(tick);
}

function stopClock() {
  if (syncRaf) cancelAnimationFrame(syncRaf);
  syncRaf = 0;
}

/** @param {number} cid @param {HTMLElement} btn */
function pickChoice(cid, btn) {
  if (!session.running || session.locked) return;
  const line = currentLine();
  const item = currentQuestion(line);
  if (!line || !item || session.answers[item.id] != null) return;
  session.locked = true;
  session.answers[item.id] = cid;
  markChoices(item, cid);
  if (cid === item.answer) {
    session.combo += 1;
    session.maxCombo = Math.max(session.maxCombo, session.combo);
    celebrateCorrect(btn, { line: true });
  } else {
    session.combo = 0;
    playMissSfx();
  }
  paintCombo();
}

export function paintQuizHome() {
  session.running = false;
  session.locked = false;
  paintMeta();
  paintClock(0);
  $("learnQuizSrc").textContent = "";
  $("learnQuizRoma").textContent = "";
  $("learnQuizRoma").hidden = true;
  $("learnQuizQs").innerHTML = "";
  $("learnQuizCombo").textContent = t("learn.quizLive");
  $("learnQuizSkip").disabled = true;
}

export async function runQuiz() {
  if (session.running) return null;
  const quiz = session.quiz;
  const list = quiz && quiz.lines;
  if (!list || !list.length) return null;
  session.running = true;
  session.answers = {};
  session.combo = 0;
  session.maxCombo = 0;
  session.locked = false;
  $("learnQuizSkip").disabled = false;
  showLine(0);
  try {
    const playing = playCueWindow(list[0].start_ms, list[list.length - 1].end_ms, { vocal: true });
    startClock();
    await playing;
    if (!session.running) return null;
    flushEnded(list[list.length - 1].end_ms);
    const bar = $("learnQuizBar");
    if (bar) bar.style.width = "100%";
    return quizScore();
  } finally {
    session.running = false;
    session.locked = false;
    stopClock();
    $("learnQuizSkip").disabled = true;
  }
}

export function quizScore() {
  const counts = { meaning: [0, 0], word: [0, 0], listen: [0, 0] };
  let ok = 0;
  let total = 0;
  for (const line of lines()) {
    const item = currentQuestion(line);
    if (!item) continue;
    total += 1;
    const bucket = counts[item.kind] || counts.listen;
    bucket[1] += 1;
    if (session.answers[item.id] === item.answer) {
      ok += 1;
      bucket[0] += 1;
    }
  }
  const pct = total ? Math.round((ok / total) * 100) : 0;
  return { ok, total, pct, counts, maxCombo: session.maxCombo };
}

/** @param {LearnQuiz} pack */
export function startQuiz(pack) {
  resetQuiz(pack);
  paintQuizHome();
}

export function stopQuiz() {
  session.running = false;
  stopClock();
  cancelCueWindow();
}

export function skipQuizLine() {
  const audio = $("playerAudio");
  const list = lines();
  if (!session.running || !audio || !list.length) return;
  const ms = (audio.currentTime || 0) * 1000;
  const live = lineAt(ms);
  const idx = live >= 0 ? live : session.line;
  const item = currentQuestion(list[idx]);
  if (item && session.answers[item.id] == null) missQuestion(item);
  const next = list[idx + 1];
  try {
    audio.currentTime = (next ? next.start_ms : list[idx].end_ms) / 1000;
  } catch (err) {}
}

/** @param {any} score @param {(pct: number) => string} grade */
export function quizScoreView(score, grade) {
  const counts = score.counts || {};
  const bits = [];
  if (counts.meaning && counts.meaning[1]) bits.push(t("learn.score.meaning", { ok: counts.meaning[0], n: counts.meaning[1] }));
  if (counts.word && counts.word[1]) bits.push(t("learn.score.word", { ok: counts.word[0], n: counts.word[1] }));
  if (counts.listen && counts.listen[1]) bits.push(t("learn.score.listen", { ok: counts.listen[0], n: counts.listen[1] }));
  if (score.maxCombo) bits.push(`COMBO ${score.maxCombo}`);
  return {
    title: t("learn.score.quiz"),
    again: t("learn.again.quiz"),
    sub: `${grade(score.pct)} · ${score.ok}/${score.total}`,
    detail: bits.join(" · "),
    celebrate: score.pct >= 70,
  };
}

export function bindQuiz() {
  $("learnQuizSkip").onclick = () => skipQuizLine();
}
