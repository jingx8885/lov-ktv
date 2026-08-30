import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { startPhoneMic } from "../playback/mic.js";
import { applyPlayerVocalMix, pausePlayer, unlockPlayerGesture } from "../playback/controls.js";
import { kickPlayerPaint } from "../playback/lyrics.js";
import { applyLearnRate, cancelCueWindow, loadLearnDiff, resetLearnRate, setLearnDiff } from "./play.js";
import { cancelCountdown, celebrateCorrect, clearLearnFx, runCountdown } from "./fx.js";
import { bindQuiz, runQuiz, startQuiz, stopQuiz, quizScoreView } from "./quiz.js";
import { bindEcho, runEcho, startEcho, stopEcho, echoScoreView } from "./echo.js";
import { bindTap, runTap, startTap, stopTap, tapScoreView } from "./tap.js";
import { bindCampaign, loadCampaign, paintCampaign, setCampaign } from "./campaign.js";
import { bindLesson, lessonScoreView, runLesson, startLesson, stopLesson } from "./lesson.js";

/** @type {{ mode: LearnMode | "lesson" | "", pack: LearnQuiz | null, vocalWas: number, boot: number, run: { unitId: string, skill: string, review?: boolean } | null, lesson: any }} */
const ui = { mode: "", pack: null, vocalWas: 1, boot: 0, run: null, lesson: null };

/** @type {Record<string, { pane: string, setup: (pack: LearnQuiz) => any, run: () => Promise<any>, stop: () => void, score: (score: any, grade: (pct: number) => string) => LearnScoreView }>} */
const MODES = {
  quiz: { pane: "learnQuiz", setup: startQuiz, run: runQuiz, stop: stopQuiz, score: quizScoreView },
  tap: { pane: "learnTap", setup: startTap, run: runTap, stop: stopTap, score: tapScoreView },
  echo: { pane: "learnEcho", setup: startEcho, run: runEcho, stop: stopEcho, score: echoScoreView }
};
const CYCLE = ["quiz", "tap", "echo"];
const PANES = ["learnHome", "learnQuiz", "learnTap", "learnEcho", "learnScore", "learnLesson", "learnBook"];

function showPane(id) {
  PANES.forEach((name) => {
    const el = $(name);
    if (el) el.hidden = name !== id;
  });
  const lyric = $("learnLyricMode");
  if (lyric) lyric.hidden = id === "learnHome" || id === "learnScore" || id === "learnBook";
}

function restoreVocal() {
  state.playerVocal = ui.vocalWas ? 1 : 0;
  const btn = $("playerVocal");
  if (btn) {
    btn.classList.toggle("on", !!state.playerVocal);
    $("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
  }
  applyPlayerVocalMix();
}

function paintDiff() {
  const cur = loadLearnDiff();
  document.querySelectorAll("[data-learn-diff]").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.learnDiff === cur);
  });
}

export function isLearnOpen() {
  return document.body.classList.contains("learn-on");
}

function stopModes() {
  ui.boot += 1;
  cancelCountdown();
  Object.values(MODES).forEach((mode) => mode.stop());
  stopLesson();
  cancelCueWindow();
}

export function exitLearn() {
  if (!isLearnOpen()) return;
  stopModes();
  clearLearnFx();
  resetLearnRate();
  ui.mode = "";
  ui.run = null;
  ui.lesson = null;
  document.body.classList.remove("learn-on");
  $("playerLearn").hidden = true;
  restoreVocal();
  kickPlayerPaint();
}

function openLearnShell() {
  api.exitEdit();
  pausePlayer();
  ui.vocalWas = state.playerVocal ? 1 : 0;
  document.body.classList.add("learn-on");
  $("playerLearn").hidden = false;
  $("learnTitle").textContent = t("learn.title");
  $("learnMeta").textContent = state.playerSong ? `${state.playerSong.title}` : "";
  $("learnSong").textContent = state.playerSong ? state.playerSong.title : "";
  paintDiff();
}

function gradeLabel(pct) {
  if (pct >= 90) return t("learn.grade.s");
  if (pct >= 75) return t("learn.grade.a");
  if (pct >= 55) return t("learn.grade.b");
  return t("learn.grade.c");
}

function nextMode(mode) {
  const index = CYCLE.indexOf(mode);
  return CYCLE[(index + 1) % CYCLE.length];
}

function otherLabel(mode) {
  if (ui.run) return ui.run.review ? t("learn.go.book") : t("learn.backPath");
  const next = nextMode(mode);
  if (next === "tap") return t("learn.go.tap");
  if (next === "echo") return t("learn.go.echo");
  return t("learn.go.quiz");
}

function goHome() {
  stopModes();
  restoreVocal();
  resetLearnRate();
  ui.mode = "";
  ui.run = null;
  ui.lesson = null;
  showPane("learnHome");
  $("learnTitle").textContent = t("learn.title");
  $("learnMeta").textContent = state.playerSong ? state.playerSong.title : "";
  paintDiff();
  loadCampaign(true).then((data) => {
    if (data) paintCampaign(data);
  });
}

/** @param {any} score */
function showScore(score) {
  const spec = ui.mode === "lesson" ? { score: lessonScoreView } : MODES[ui.mode] || MODES.quiz;
  const view = spec.score(score, gradeLabel);
  showPane("learnScore");
  $("learnTitle").textContent = view.title;
  $("learnMeta").textContent = state.playerSong ? state.playerSong.title : "";
  $("learnScoreNum").textContent = String(score.pct);
  $("learnScoreSub").textContent = view.sub;
  $("learnScoreDetail").textContent = view.detail;
  $("learnAgain").textContent = view.again;
  $("learnOther").textContent = otherLabel(ui.mode);
  const mix = $("learnMix");
  mix.hidden = !view.mixUrl;
  if (view.mixUrl) {
    mix.src = view.mixUrl;
    mix.play().catch(() => {});
  } else {
    mix.removeAttribute("src");
  }
  if (view.celebrate) celebrateCorrect($("learnScoreNum"), { line: true });
}

async function loadPack() {
  if (ui.pack && ui.pack.song_id === (state.playerSong && state.playerSong.id)) return ui.pack;
  const song = state.playerSong;
  if (!song) return null;
  const { ok, status, data } = await fetchJson(`/api/songs/${song.id}/learn`);
  if (!ok) {
    showToast((data && data.detail) || (status === 409 ? t("learn.cant") : t("learn.loadFail")));
    return null;
  }
  ui.pack = data;
  return data;
}

function scopedPack(lines) {
  const pack = ui.pack || { lines: [], song_id: state.playerSong && state.playerSong.id };
  return Object.assign({}, pack, { lines: lines || pack.lines });
}

async function submitRun(score) {
  const run = ui.run;
  const song = state.playerSong;
  if (!run || !song) return;
  const path = run.review ? `/api/songs/${song.id}/learn/review` : `/api/songs/${song.id}/learn/lesson`;
  const { ok, data } = await fetchJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unit_id: run.unitId,
      skill: run.skill,
      pct: score && score.pct,
      answers: (score && score.answers) || []
    })
  });
  if (ok && data && data.campaign) setCampaign(data.campaign);
}

async function startMode(mode, pack) {
  const spec = MODES[mode] || MODES.quiz;
  const loaded = pack || (await loadPack());
  if (!loaded) return;
  stopModes();
  const boot = ui.boot;
  applyLearnRate();
  unlockPlayerGesture();
  pausePlayer();
  ui.mode = /** @type {LearnMode} */ (MODES[mode] ? mode : "quiz");
  showPane(spec.pane);
  spec.setup(loaded);
  if (ui.mode === "echo") {
    try {
      await startPhoneMic();
    } catch (err) {
      showToast((err && err.message) || t("learn.noRec"));
      ui.mode = "";
      showPane("learnHome");
      return;
    }
  }
  const go = await runCountdown();
  if (!go || boot !== ui.boot || ui.mode !== mode) return;
  const score = await spec.run();
  if (boot !== ui.boot) return;
  if (score && ui.run) await submitRun(score);
  if (score) showScore(score);
}

async function startSkill(unitId, skill) {
  const song = state.playerSong;
  if (!song) return;
  const { ok, status, data } = await fetchJson(
    `/api/songs/${song.id}/learn/lesson?unit=${encodeURIComponent(unitId)}&skill=${encodeURIComponent(skill)}`
  );
  if (!ok) {
    showToast((data && data.detail) || (status === 409 ? t("learn.cant") : t("learn.loadFail")));
    return;
  }
  ui.run = { unitId, skill };
  ui.lesson = data;
  if (data.play_mode === "tap" || data.play_mode === "echo") {
    const pack = await loadPack();
    if (!pack) return;
    return startMode(data.play_mode, scopedPack(data.lines || pack.lines));
  }
  await startLessonRun(data);
}

async function startLessonRun(lesson) {
  if (!lesson || !(lesson.items || []).length) {
    showToast(t("learn.cant"));
    return;
  }
  stopModes();
  const boot = ui.boot;
  applyLearnRate();
  unlockPlayerGesture();
  pausePlayer();
  ui.mode = "lesson";
  showPane("learnLesson");
  startLesson(lesson);
  const go = await runCountdown();
  if (!go || boot !== ui.boot || ui.mode !== "lesson") return;
  const score = await runLesson();
  if (boot !== ui.boot) return;
  if (score) await submitRun(score);
  if (score) showScore(score);
}

async function openBook() {
  const song = state.playerSong;
  if (!song) return;
  const { ok, data } = await fetchJson(`/api/songs/${song.id}/learn/mistakes`);
  if (!ok) {
    showToast((data && data.detail) || t("learn.loadFail"));
    return;
  }
  const list = $("learnBookList");
  const lead = $("learnBookLead");
  const rows = (data && data.mistakes) || [];
  if (lead) lead.textContent = rows.length ? t("learn.bookHint", { n: rows.length }) : t("learn.bookEmpty");
  if (list) {
    list.innerHTML = rows
      .map((row) => {
        const kind =
          row.qkind === "listen"
            ? t("learn.skill.listen")
            : row.qkind === "meaning" || row.qkind === "reverse"
              ? t("learn.skill.sentence")
              : t("learn.skill.word");
        return `
      <article class="learn-book-item">
        <i>${escapeHtml(kind)} · ${escapeHtml(t("learn.practice"))} ${row.correct_streak || 0}/2</i>
        <b>${escapeHtml(row.stem || row.item_key || "")}</b>
        <span>${escapeHtml(row.answer_text || row.prompt || "")}</span>
      </article>
    `;
      })
      .join("");
  }
  ui.mode = "";
  showPane("learnBook");
  $("learnTitle").textContent = t("learn.book");
  $("learnMeta").textContent = state.playerSong ? state.playerSong.title : "";
}

async function startReview() {
  const song = state.playerSong;
  if (!song) return;
  const { ok, status, data } = await fetchJson(`/api/songs/${song.id}/learn/review`);
  if (!ok) {
    showToast((data && data.detail) || (status === 409 ? t("learn.bookEmpty") : t("learn.loadFail")));
    return;
  }
  ui.run = { unitId: "review", skill: "review", review: true };
  ui.lesson = data;
  await startLessonRun(data);
}

export async function enterLearn() {
  if (!state.playerSong) return showToast(t("phone.player.needSong"));
  if (!(state.playerLyrics && state.playerLyrics.cues && state.playerLyrics.cues.length)) {
    return showToast(t("learn.needLyrics"));
  }
  openLearnShell();
  showPane("learnHome");
  const data = await loadCampaign(true);
  if (data) paintCampaign(data);
}

export function bindLearn() {
  document.querySelectorAll("[data-enter-learn]").forEach((btn) => {
    btn.onclick = () => {
      if (!state.playerSong) return showToast(t("phone.player.needSong"));
      if (!(state.playerLyrics && state.playerLyrics.cues && state.playerLyrics.cues.length)) {
        return showToast(t("learn.needLyrics"));
      }
      if (state.currentPage !== "player") api.showPage("player");
      enterLearn();
    };
  });
  $("learnBack").onclick = () => {
    if ($("learnHome").hidden) {
      goHome();
      return;
    }
    exitLearn();
  };
  document.querySelectorAll("[data-learn-diff]").forEach((btn) => {
    btn.onclick = () => {
      setLearnDiff(btn.dataset.learnDiff);
      paintDiff();
    };
  });
  document.querySelectorAll("[data-learn-mode]").forEach((btn) => {
    btn.addEventListener("pointerdown", () => unlockPlayerGesture());
    btn.onclick = () => {
      ui.run = null;
      startMode(btn.dataset.learnMode);
    };
  });
  bindQuiz();
  bindTap();
  bindEcho();
  bindLesson();
  bindCampaign({
    onSkill: (unitId, skill) => startSkill(unitId, skill),
    onBook: () => openBook()
  });
  const bookGo = $("learnBookGo");
  if (bookGo) bookGo.onclick = () => startReview();
  $("learnAgain").onclick = () => {
    $("learnMix").pause();
    if (ui.run && ui.run.review) return startReview();
    if (ui.run && ui.mode === "lesson") return startSkill(ui.run.unitId, ui.run.skill);
    if (ui.run && (ui.mode === "tap" || ui.mode === "echo")) return startSkill(ui.run.unitId, ui.run.skill);
    startMode(ui.mode);
  };
  $("learnOther").onclick = () => {
    $("learnMix").pause();
    if (ui.run) {
      if (ui.run.review) return openBook();
      return goHome();
    }
    startMode(nextMode(ui.mode));
  };
  $("learnDone").onclick = () => exitLearn();
}
