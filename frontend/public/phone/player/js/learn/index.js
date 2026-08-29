import { $ } from "../../../../shared/ui/js/dom.js";
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

/** @type {{ mode: LearnMode | "", pack: LearnQuiz | null, vocalWas: number, boot: number }} */
const ui = { mode: "", pack: null, vocalWas: 1, boot: 0 };

/** @type {Record<string, { pane: string, setup: (pack: LearnQuiz) => any, run: () => Promise<any>, stop: () => void, score: (score: any, grade: (pct: number) => string) => LearnScoreView }>} */
const MODES = {
  quiz: { pane: "learnQuiz", setup: startQuiz, run: runQuiz, stop: stopQuiz, score: quizScoreView },
  tap: { pane: "learnTap", setup: startTap, run: runTap, stop: stopTap, score: tapScoreView },
  echo: { pane: "learnEcho", setup: startEcho, run: runEcho, stop: stopEcho, score: echoScoreView }
};
const CYCLE = ["quiz", "tap", "echo"];
const PANES = ["learnHome", "learnQuiz", "learnTap", "learnEcho", "learnScore"];

function showPane(id) {
  PANES.forEach((name) => {
    const el = $(name);
    if (el) el.hidden = name !== id;
  });
  const lyric = $("learnLyricMode");
  if (lyric) lyric.hidden = id === "learnHome" || id === "learnScore";
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
  cancelCueWindow();
}

export function exitLearn() {
  if (!isLearnOpen()) return;
  stopModes();
  clearLearnFx();
  resetLearnRate();
  ui.mode = "";
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
  const next = nextMode(mode);
  if (next === "tap") return t("learn.go.tap");
  if (next === "echo") return t("learn.go.echo");
  return t("learn.go.quiz");
}

/** @param {any} score */
function showScore(score) {
  const spec = MODES[ui.mode] || MODES.quiz;
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

async function startMode(mode) {
  const spec = MODES[mode] || MODES.quiz;
  const pack = await loadPack();
  if (!pack) return;
  stopModes();
  const boot = ui.boot;
  applyLearnRate();
  unlockPlayerGesture();
  pausePlayer();
  ui.mode = /** @type {LearnMode} */ (MODES[mode] ? mode : "quiz");
  showPane(spec.pane);
  spec.setup(pack);
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
  if (score) showScore(score);
}

export async function enterLearn() {
  if (!state.playerSong) return showToast(t("phone.player.needSong"));
  if (!(state.playerLyrics && state.playerLyrics.cues && state.playerLyrics.cues.length)) {
    return showToast(t("learn.needLyrics"));
  }
  openLearnShell();
  showPane("learnHome");
}

export function bindLearn() {
  document.querySelectorAll("[data-enter-learn]").forEach((btn) => {
    btn.onclick = () => {
      // 没有可玩的歌曲时不要先切到播放器，避免“游戏”点击看起来像跳到了听歌页。
      if (!state.playerSong) return showToast(t("phone.player.needSong"));
      if (!(state.playerLyrics && state.playerLyrics.cues && state.playerLyrics.cues.length)) {
        return showToast(t("learn.needLyrics"));
      }
      if (state.currentPage !== "player") api.showPage("player");
      enterLearn();
    };
  });
  $("learnBack").onclick = () => {
    if (ui.mode && $("learnHome").hidden) {
      stopModes();
      restoreVocal();
      resetLearnRate();
      ui.mode = "";
      showPane("learnHome");
      $("learnTitle").textContent = t("learn.title");
      $("learnMeta").textContent = state.playerSong ? state.playerSong.title : "";
      paintDiff();
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
    btn.onclick = () => startMode(btn.dataset.learnMode);
  });
  bindQuiz();
  bindTap();
  bindEcho();
  $("learnAgain").onclick = () => {
    $("learnMix").pause();
    startMode(ui.mode);
  };
  $("learnOther").onclick = () => {
    $("learnMix").pause();
    startMode(nextMode(ui.mode));
  };
  $("learnDone").onclick = () => exitLearn();
}
