import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { applyPlayerVocalMix, pausePlayer } from "./playback.js";
import { cancelCueWindow } from "./learn-play.js";
import { advanceQuiz, quizScore, replayQuizLine, resetQuiz, showQuizLine } from "./learn-quiz.js";
import { echoBusy, paintEchoHome, resetEcho, runEcho, skipEchoLine, stopEcho } from "./learn-echo.js";

/** @type {{ mode: LearnMode | "", quiz: LearnQuiz | null, scoreKind: string, vocalWas: number }} */
const ui = { mode: "", quiz: null, scoreKind: "", vocalWas: 1 };

function showPane(id) {
  ["learnHome", "learnQuiz", "learnEcho", "learnScore"].forEach((name) => {
    const el = $(name);
    if (el) el.hidden = name !== id;
  });
}

function restoreVocal() {
  state.playerVocal = state.learnVocalWas ? 1 : 0;
  const btn = $("playerVocal");
  if (btn) {
    btn.classList.toggle("on", !!state.playerVocal);
    $("playerVocalLabel").textContent = state.playerVocal ? "原唱" : "伴奏";
  }
  applyPlayerVocalMix();
}

export function exitLearn() {
  if (!state.learnOpen) return;
  stopEcho();
  cancelCueWindow();
  state.learnOpen = false;
  ui.mode = "";
  document.body.classList.remove("learn-on");
  $("playerLearn").hidden = true;
  restoreVocal();
}

function openLearnShell() {
  api.exitEdit();
  pausePlayer();
  state.learnVocalWas = state.playerVocal ? 1 : 0;
  state.learnOpen = true;
  document.body.classList.add("learn-on");
  $("playerLearn").hidden = false;
  $("learnTitle").textContent = "学习";
  $("learnMeta").textContent = state.playerSong ? `${state.playerSong.title}` : "";
}

function gradeLabel(pct) {
  if (pct >= 90) return "几乎全对";
  if (pct >= 75) return "很稳";
  if (pct >= 55) return "过得去";
  return "再听两遍";
}

/** @param {{ pct: number, ok?: number, total?: number, counts?: any, sung?: number, mixUrl?: string }} score */
function showScore(score) {
  showPane("learnScore");
  $("learnTitle").textContent = ui.mode === "echo" ? "跟唱得分" : "测验得分";
  $("learnMeta").textContent = state.playerSong ? state.playerSong.title : "";
  $("learnScoreNum").textContent = String(score.pct);
  if (ui.mode === "echo") {
    $("learnScoreSub").textContent = `${gradeLabel(score.pct)} · 唱了 ${score.sung || 0}/${score.total || 0} 句`;
    $("learnScoreDetail").textContent = "按音量和节奏贴合度估的，当个练习参考。";
    const mix = $("learnMix");
    mix.hidden = !score.mixUrl;
    if (score.mixUrl) {
      mix.src = score.mixUrl;
      mix.play().catch(() => {});
    }
  } else {
    const counts = score.counts || {};
    const bits = [];
    if (counts.meaning && counts.meaning[1]) bits.push(`句意 ${counts.meaning[0]}/${counts.meaning[1]}`);
    if (counts.word && counts.word[1]) bits.push(`单词 ${counts.word[0]}/${counts.word[1]}`);
    if (counts.listen && counts.listen[1]) bits.push(`听写 ${counts.listen[0]}/${counts.listen[1]}`);
    $("learnScoreSub").textContent = `${gradeLabel(score.pct)} · ${score.ok}/${score.total}`;
    $("learnScoreDetail").textContent = bits.join(" · ");
    $("learnMix").hidden = true;
    $("learnMix").removeAttribute("src");
  }
  $("learnAgain").textContent = ui.mode === "echo" ? "再唱一遍" : "再测一遍";
  $("learnOther").textContent = ui.mode === "echo" ? "去做测验" : "去跟唱";
}

async function loadQuiz() {
  if (ui.quiz && ui.quiz.song_id === (state.playerSong && state.playerSong.id)) return ui.quiz;
  const song = state.playerSong;
  if (!song) return null;
  const { ok, status, data } = await fetchJson(`/api/songs/${song.id}/learn`);
  if (!ok) {
    showToast((data && data.detail) || (status === 409 ? "这首还不能学" : "学习内容加载失败"));
    return null;
  }
  ui.quiz = data;
  return data;
}

async function startQuiz() {
  const quiz = await loadQuiz();
  if (!quiz) return;
  ui.mode = "quiz";
  resetQuiz(quiz);
  showPane("learnQuiz");
  await showQuizLine();
}

async function startEcho() {
  const quiz = await loadQuiz();
  if (!quiz) return;
  ui.mode = "echo";
  resetEcho(quiz.lines);
  showPane("learnEcho");
  paintEchoHome();
}

export async function enterLearn() {
  if (!state.playerSong) return showToast("先从点歌台听一首");
  if (!(state.playerLyrics && state.playerLyrics.cues && state.playerLyrics.cues.length)) {
    return showToast("这首还没有歌词");
  }
  openLearnShell();
  showPane("learnHome");
}

export function bindLearn() {
  $("playerLearnBtn").onclick = () => enterLearn();
  $("learnBack").onclick = () => {
    if (ui.mode && $("learnHome").hidden) {
      stopEcho();
      cancelCueWindow();
      restoreVocal();
      ui.mode = "";
      showPane("learnHome");
      $("learnTitle").textContent = "学习";
      $("learnMeta").textContent = state.playerSong ? state.playerSong.title : "";
      return;
    }
    exitLearn();
  };
  document.querySelectorAll("[data-learn-mode]").forEach((btn) => {
    btn.onclick = () => {
      if (btn.dataset.learnMode === "echo") startEcho();
      else startQuiz();
    };
  });
  $("learnReplay").onclick = () => replayQuizLine();
  $("learnQuizNext").onclick = async () => {
    const next = advanceQuiz();
    if (next === "line") await showQuizLine();
    if (next === "score") showScore(quizScore());
  };
  $("learnEchoGo").onclick = async () => {
    if (echoBusy()) return;
    const score = await runEcho();
    if (score) showScore(score);
  };
  $("learnEchoSkip").onclick = () => skipEchoLine();
  $("learnAgain").onclick = () => {
    $("learnMix").pause();
    if (ui.mode === "echo") startEcho();
    else startQuiz();
  };
  $("learnOther").onclick = () => {
    $("learnMix").pause();
    if (ui.mode === "echo") startQuiz();
    else startEcho();
  };
  $("learnDone").onclick = () => exitLearn();
}
