import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { showToast } from "../../ui/js/toast.js";
import { playCueWindow } from "./learn-play.js";

/** @type {LearnSession} */
const session = {
  quiz: null,
  line: 0,
  answers: {},
};

/** @param {LearnQuiz} quiz */
export function resetQuiz(quiz) {
  session.quiz = quiz;
  session.line = 0;
  session.answers = {};
}

export function quizProgress() {
  const quiz = session.quiz;
  if (!quiz || !quiz.lines.length) return { line: 0, lines: 0, done: 0, total: 0 };
  const done = Object.keys(session.answers).length;
  return { line: session.line, lines: quiz.lines.length, done, total: quiz.total_questions };
}

function currentLine() {
  return session.quiz && session.quiz.lines[session.line];
}

function lineAnswered(line) {
  return (line.questions || []).every((item) => session.answers[item.id] != null);
}

function paintProgress() {
  const { line, lines } = quizProgress();
  const bar = $("learnQuizBar");
  if (bar) bar.style.width = lines ? `${Math.round(((line + (lineAnswered(currentLine() || { questions: [] }) ? 1 : 0)) / lines) * 100)}%` : "0";
}

/** @param {LearnLine} line */
function renderQuestions(line) {
  const box = $("learnQuizQs");
  box.innerHTML = (line.questions || []).map((item) => `
    <article class="learn-q" data-qid="${escapeHtml(item.id)}">
      <b>${escapeHtml(item.prompt)}</b>
      <div class="learn-choices">
        ${(item.choices || []).map((choice) => `
          <button type="button" class="learn-choice" data-qid="${escapeHtml(item.id)}" data-cid="${choice.id}">${escapeHtml(choice.text)}</button>
        `).join("")}
      </div>
    </article>
  `).join("");
  box.querySelectorAll(".learn-choice").forEach((btn) => {
    btn.addEventListener("pointerdown", () => btn.classList.add("is-on"));
    btn.addEventListener("pointerup", () => btn.classList.remove("is-on"));
    btn.addEventListener("pointercancel", () => btn.classList.remove("is-on"));
    btn.onclick = () => answerQuestion(btn.dataset.qid, Number(btn.dataset.cid));
  });
  (line.questions || []).forEach((item) => {
    if (session.answers[item.id] != null) paintAnswered(item);
  });
}

/** @param {LearnQuestion} item */
function paintAnswered(item) {
  const picked = session.answers[item.id];
  $("learnQuizQs").querySelectorAll(`[data-qid="${item.id}"]`).forEach((btn) => {
    if (!btn.classList.contains("learn-choice")) return;
    const cid = Number(btn.dataset.cid);
    btn.disabled = true;
    btn.classList.toggle("is-ok", cid === item.answer);
    btn.classList.toggle("is-no", cid === picked && picked !== item.answer);
  });
}

function answerQuestion(qid, cid) {
  const line = currentLine();
  if (!line || session.answers[qid] != null) return;
  const item = (line.questions || []).find((q) => q.id === qid);
  if (!item) return;
  session.answers[qid] = cid;
  paintAnswered(item);
  $("learnQuizNext").disabled = !lineAnswered(line);
  paintProgress();
}

export async function showQuizLine() {
  const line = currentLine();
  const quiz = session.quiz;
  if (!line || !quiz) return;
  $("learnTitle").textContent = "歌词测验";
  $("learnMeta").textContent = `${line.index + 1} / ${quiz.lines.length} · 每句 ${line.questions.length} 题`;
  $("learnQuizSrc").textContent = line.text;
  $("learnQuizRoma").textContent = line.romaji || "";
  $("learnQuizRoma").hidden = !line.romaji;
  $("learnQuizNext").disabled = !lineAnswered(line);
  $("learnQuizNext").textContent = session.line >= quiz.lines.length - 1 ? "看得分" : "下一句";
  renderQuestions(line);
  paintProgress();
  await playCueWindow(line.start_ms, line.end_ms, { vocal: true });
}

export async function replayQuizLine() {
  const line = currentLine();
  if (!line) return;
  await playCueWindow(line.start_ms, line.end_ms, { vocal: true });
}

/** @returns {"line" | "score" | ""} */
export function advanceQuiz() {
  const line = currentLine();
  if (!line) return "";
  if (!lineAnswered(line)) {
    showToast("先答完这句的题");
    return "";
  }
  if (session.line < session.quiz.lines.length - 1) {
    session.line += 1;
    return "line";
  }
  return "score";
}

export function quizScore() {
  const quiz = session.quiz;
  const counts = { meaning: [0, 0], word: [0, 0], listen: [0, 0] };
  let ok = 0;
  let total = 0;
  for (const line of (quiz && quiz.lines) || []) {
    for (const item of line.questions || []) {
      total += 1;
      const bucket = counts[item.kind] || counts.listen;
      bucket[1] += 1;
      if (session.answers[item.id] === item.answer) {
        ok += 1;
        bucket[0] += 1;
      }
    }
  }
  const pct = total ? Math.round((ok / total) * 100) : 0;
  return { ok, total, pct, counts };
}
