import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { songArtist, songTitle } from "../../../../shared/ui/js/song.js";
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
import { getStudyWords } from "../../../desk/js/lyrics.js";

/** @type {{ mode: LearnMode | "lesson" | "", pack: LearnQuiz | null, vocalWas: number, boot: number, generation: number, run: { unitId: string, skill: string, review?: boolean } | null, lesson: any, attemptId: string, pendingScore: any }} */
const ui = {
  mode: "",
  pack: null,
  vocalWas: 1,
  boot: 0,
  generation: 0,
  run: null,
  lesson: null,
  attemptId: "",
  pendingScore: null
};
let libraryLoad = 0;

/** @type {Record<string, { pane: string, setup: (pack: LearnQuiz) => any, run: () => Promise<any>, stop: () => void, score: (score: any, grade: (pct: number) => string) => LearnScoreView }>} */
const MODES = {
  quiz: { pane: "learnQuiz", setup: startQuiz, run: runQuiz, stop: stopQuiz, score: quizScoreView },
  tap: { pane: "learnTap", setup: startTap, run: runTap, stop: stopTap, score: tapScoreView },
  echo: { pane: "learnEcho", setup: startEcho, run: runEcho, stop: stopEcho, score: echoScoreView }
};
const CYCLE = ["quiz", "tap", "echo"];
const PANES = [
  "learnLibrary",
  "learnHome",
  "learnQuiz",
  "learnTap",
  "learnEcho",
  "learnScore",
  "learnLesson",
  "learnBook"
];

function showPane(id) {
  PANES.forEach((name) => {
    const el = $(name);
    if (el) el.hidden = name !== id;
  });
  const lyric = $("learnLyricMode");
  if (lyric) lyric.hidden = id === "learnLibrary" || id === "learnHome" || id === "learnScore" || id === "learnBook";
  const shell = $("playerLearn");
  if (shell) shell.classList.toggle("is-library", id === "learnLibrary");
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

function syncLearnNav(active) {
  const learnBtn = $("tabLearn");
  if (learnBtn) learnBtn.classList.toggle("on", !!active);
  if (active) {
    document.querySelectorAll("[data-nav]").forEach((btn) => btn.classList.remove("on"));
  } else {
    const current = state.currentPage;
    document.querySelectorAll("[data-nav]").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.nav === current);
    });
  }
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
  ui.generation += 1;
  stopModes();
  clearLearnFx();
  resetLearnRate();
  ui.mode = "";
  ui.pack = null;
  ui.run = null;
  ui.lesson = null;
  ui.attemptId = "";
  ui.pendingScore = null;
  document.body.classList.remove("learn-on");
  $("playerLearn").hidden = true;
  $("topTitle").textContent = t("phone.nav.player");
  syncLearnNav(false);
  restoreVocal();
  kickPlayerPaint();
}

function openLearnShell() {
  api.exitEdit();
  pausePlayer();
  ui.vocalWas = state.playerVocal ? 1 : 0;
  document.body.classList.add("learn-on");
  $("playerLearn").hidden = false;
  $("topTitle").textContent = t("learn.pageTitle");
  syncLearnNav(true);
  paintSongHead();
  paintDiff();
}

/**
 * The shell topbar already reads "学歌", so the in-page bar names the song
 * instead of repeating the section title.
 */
function paintSongHead() {
  const song = state.playerSong;
  $("learnTitle").textContent = song ? songTitle(song) : t("learn.pageTitle");
  $("learnMeta").textContent = song ? songArtist(song) : "";
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
  ui.generation += 1;
  stopModes();
  restoreVocal();
  resetLearnRate();
  ui.mode = "";
  ui.run = null;
  ui.lesson = null;
  ui.attemptId = "";
  ui.pendingScore = null;
  showPane("learnHome");
  paintSongHead();
  paintDiff();
  loadCampaign(true).then((data) => {
    if (data) paintCampaign(data);
  });
}

function campaignProgress(data) {
  const goal = data && data.goal;
  if (!goal) return { pct: 0, done: false };
  const slices = [goal.words, goal.sentences, goal.read, goal.sing].filter(Boolean);
  const total = slices.reduce((sum, item) => sum + Number(item.total || 0), 0);
  const done = slices.reduce((sum, item) => sum + Math.min(Number(item.done || 0), Number(item.total || 0)), 0);
  return { pct: total ? Math.round((done / total) * 100) : 0, done: !!goal.cleared };
}

function paintLearnSongList(songs, campaigns) {
  const list = $("learnSongList");
  const count = $("learnLibraryCount");
  if (!list) return;
  const ready = (songs || []).filter((song) => song && song.status === "ready");
  if (count) count.textContent = ready.length ? t("learn.songCount", { n: ready.length }) : "";
  if (!ready.length) {
    list.innerHTML = `<div class="empty-state"><p>${escapeHtml(t("learn.noAddedSongs"))}</p><button class="btn primary" type="button" data-go-search>${escapeHtml(t("learn.searchMore"))}</button></div>`;
    list.querySelector("[data-go-search]")?.addEventListener("click", () => api.showPage("search"));
    return;
  }
  list.innerHTML = ready
    .map((song) => {
      const progress = campaignProgress(campaigns.get(song.id));
      const current = state.playerSong && state.playerSong.id === song.id;
      return `<button type="button" class="learn-song-row${progress.done ? " is-complete" : ""}${current ? " is-current" : ""}" data-learn-song="${escapeHtml(song.id)}">
        <span class="learn-song-cover">${progress.done ? "✓" : "♪"}</span>
        <span class="learn-song-copy"><b>${escapeHtml(songTitle(song))}</b><small>${escapeHtml(songArtist(song) || t("common.unknownArtist"))}</small></span>
        <span class="learn-song-progress"><i style="--pct:${progress.pct}%"></i><em>${progress.done ? escapeHtml(t("learn.completed")) : `${progress.pct}%`}</em></span>
      </button>`;
    })
    .join("");
  list.querySelectorAll("[data-learn-song]").forEach((btn) => {
    btn.onclick = () => selectLearnSong(btn.dataset.learnSong);
  });
}

async function loadLearnLibrary(query = "") {
  const loadId = ++libraryLoad;
  const list = $("learnSongList");
  if (list && !query) list.innerHTML = `<div class="empty-state"><p>${escapeHtml(t("common.loading"))}</p></div>`;
  const params = query ? `?q=${encodeURIComponent(query)}&page=1&count=20` : "";
  const response = await fetchJson("/api/songs" + params, { cache: "no-store" }).catch(() => null);
  if (loadId !== libraryLoad) return;
  if (!response || !response.ok) {
    if (!query && api.loadSongs) await api.loadSongs(false, true).catch(() => {});
    const fallback = !query && Array.isArray(state.libSongs) ? state.libSongs : [];
    if (fallback.length) {
      paintLearnSongList(fallback, new Map());
    } else if (list) {
      list.innerHTML = `<div class="empty-state"><p>${escapeHtml(t("common.loadFailed"))}</p><button class="btn" type="button" data-learn-retry>${escapeHtml(t("learn.retry"))}</button></div>`;
      list.querySelector("[data-learn-retry]")?.addEventListener("click", () => loadLearnLibrary(query));
    }
    return;
  }
  const payload = response.data || {};
  const songs = Array.isArray(payload) ? payload : payload.songs || [];
  const ready = songs.filter((song) => song && song.status === "ready");
  // 先把曲目列表画出来，进度接口慢或部分歌曲没有学习数据时也不阻塞整个页面。
  paintLearnSongList(songs, new Map());
  const campaigns = new Map();
  await Promise.all(
    ready.map(async (song) => {
      const result = await fetchJson(`/api/songs/${encodeURIComponent(song.id)}/learn/campaign`, {
        cache: "no-store"
      }).catch(() => null);
      if (result && result.ok && result.data) campaigns.set(song.id, result.data);
    })
  );
  if (loadId !== libraryLoad) return;
  paintLearnSongList(songs, campaigns);
}

async function selectLearnSong(songId) {
  if (!songId || !api.loadPlayerSong) return;
  ui.pack = null;
  syncLearnNav(true);
  await api.loadPlayerSong(songId, { play: false });
  if (!state.playerSong || state.playerSong.id !== songId) return;
  if (!(state.playerLyrics && state.playerLyrics.cues && state.playerLyrics.cues.length)) {
    showToast(t("learn.needLyrics"));
    return;
  }
  showPane("learnHome");
  paintSongHead();
  const data = await loadCampaign(true, true);
  if (data) paintCampaign(data);
  else paintCampaign(null);
}

function showLearnLibrary() {
  stopModes();
  restoreVocal();
  resetLearnRate();
  ui.mode = "";
  ui.pack = null;
  ui.run = null;
  ui.lesson = null;
  showPane("learnLibrary");
  $("topTitle").textContent = t("learn.pageTitle");
  $("learnTitle").textContent = t("learn.pageTitle");
  $("learnMeta").textContent = "";
  if ($("learnSongSearch")) $("learnSongSearch").value = "";
  if ($("learnSongSearchClear")) $("learnSongSearchClear").hidden = true;
  loadLearnLibrary();
}

/** @param {any} score */
function showScore(score) {
  const spec = ui.mode === "lesson" ? { score: lessonScoreView } : MODES[ui.mode] || MODES.quiz;
  const view = spec.score(score, gradeLabel);
  showPane("learnScore");
  $("learnTitle").textContent = view.title;
  $("learnMeta").textContent = state.playerSong ? songTitle(state.playerSong) : "";
  $("learnScoreNum").textContent = String(score.pct);
  $("learnScoreSub").textContent = view.sub;
  $("learnScoreDetail").textContent = view.detail;
  $("learnAgain").textContent = view.again;
  $("learnOther").textContent = otherLabel(ui.mode);
  const saveRetry = $("learnSaveRetry");
  if (saveRetry) saveRetry.hidden = !ui.pendingScore;
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
      attempt_id: ui.attemptId,
      unit_id: run.unitId,
      skill: run.skill,
      pct: score && score.pct,
      answers: (score && score.answers) || []
    })
  });
  if (ok && data && data.campaign) setCampaign(data.campaign);
  if (!ok) {
    ui.pendingScore = score;
    showToast((data && data.detail) || t("common.saveFailed"));
  } else {
    ui.pendingScore = null;
  }
  return ok;
}

async function startMode(mode, pack) {
  const spec = MODES[mode] || MODES.quiz;
  const generation = ui.generation;
  const loaded = pack || (await loadPack());
  if (!loaded || generation !== ui.generation || !isLearnOpen()) return;
  stopModes();
  const boot = ui.boot;
  applyLearnRate();
  unlockPlayerGesture();
  pausePlayer();
  ui.mode = /** @type {LearnMode} */ (MODES[mode] ? mode : "quiz");
  ui.attemptId =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : String(Date.now()) + "-" + String(Math.random());
  showPane(spec.pane);
  spec.setup(loaded);
  if (ui.mode === "echo") {
    try {
      await startPhoneMic();
    } catch (err) {
      showToast((err && err.message) || t("learn.noRec"));
      restoreVocal();
      resetLearnRate();
      ui.mode = "";
      showPane("learnHome");
      return;
    }
  }
  const go = await runCountdown();
  if (!go || boot !== ui.boot || ui.mode !== mode) return;
  const score = await spec.run();
  if (boot !== ui.boot || generation !== ui.generation || !isLearnOpen()) return;
  if (score && ui.run) await submitRun(score);
  if (score) showScore(score);
}

async function startSkill(unitId, skill) {
  const song = state.playerSong;
  if (!song) return;
  const generation = ui.generation;
  const { ok, status, data } = await fetchJson(
    `/api/songs/${song.id}/learn/lesson?unit=${encodeURIComponent(unitId)}&skill=${encodeURIComponent(skill)}`
  );
  if (!ok || generation !== ui.generation || !isLearnOpen()) {
    if (!ok) showToast((data && data.detail) || (status === 409 ? t("learn.cant") : t("learn.loadFail")));
    return;
  }
  if (!ok) {
    showToast((data && data.detail) || (status === 409 ? t("learn.cant") : t("learn.loadFail")));
    return;
  }
  ui.run = { unitId, skill };
  ui.lesson = data;
  if (data.play_mode === "tap" || data.play_mode === "echo") {
    const pack = await loadPack();
    if (!pack || generation !== ui.generation || !isLearnOpen()) return;
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
  const generation = ui.generation;
  applyLearnRate();
  unlockPlayerGesture();
  pausePlayer();
  ui.mode = "lesson";
  ui.attemptId =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : String(Date.now()) + "-" + String(Math.random());
  showPane("learnLesson");
  startLesson(lesson);
  const go = await runCountdown();
  if (!go || boot !== ui.boot || generation !== ui.generation || ui.mode !== "lesson" || !isLearnOpen()) return;
  const score = await runLesson();
  if (boot !== ui.boot || generation !== ui.generation || !isLearnOpen()) return;
  if (score) await submitRun(score);
  if (score) showScore(score);
}

export async function openStudyBook(kind = "") {
  const song = state.playerSong;
  let data = { mistakes: [] };
  if (song) {
    const response = await fetchJson(`/api/songs/${song.id}/learn/mistakes`);
    if (!response.ok) {
      showToast((response.data && response.data.detail) || t("learn.loadFail"));
      return;
    }
    data = response.data || data;
  }
  const list = $("learnBookList");
  const lead = $("learnBookLead");
  const rows = (data && data.mistakes) || [];
  const words = getStudyWords();
  if (lead) {
    lead.textContent =
      kind === "words"
        ? t("learn.wordsSummary", { n: words.length })
        : kind === "mistakes"
          ? t("learn.mistakesSummary", { n: rows.length })
          : t("learn.bookSummary", { words: words.length, mistakes: rows.length });
  }
  if (list) {
    const wordHtml =
      kind !== "mistakes" && words.length
        ? `<section class="learn-book-section"><h3>${escapeHtml(t("learn.savedWords"))}</h3>${words
            .map(
              (word) =>
                `<article class="learn-book-item is-word"><i>${escapeHtml(word.song || t("learn.savedFromLyrics"))}</i><b>${escapeHtml(word.text)}</b><span>${escapeHtml(word.zh || word.romaji || word.cue || "")}</span></article>`
            )
            .join("")}</section>`
        : "";
    const mistakeHtml =
      kind !== "words" && rows.length
        ? `<section class="learn-book-section"><h3>${escapeHtml(t("learn.mistakes"))}</h3>${rows
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
            .join("")}</section>`
        : kind === "words"
          ? `<p class="tiny learn-book-empty">${escapeHtml(words.length ? t("learn.wordsBookHint") : t("learn.bookEmpty"))}</p>`
          : `<p class="tiny learn-book-empty">${escapeHtml(t("learn.bookEmpty"))}</p>`;
    list.innerHTML = wordHtml + mistakeHtml;
  }
  ui.mode = "";
  showPane("learnBook");
  $("learnTitle").textContent =
    kind === "words" ? t("learn.wordsBook") : kind === "mistakes" ? t("learn.mistakesBook") : t("learn.book");
  $("learnMeta").textContent = state.playerSong ? songTitle(state.playerSong) : "";
  const go = $("learnBookGo");
  if (go) go.hidden = kind === "words" || !rows.length;
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
  openLearnShell();
  // 从听歌页进入时直接打开当前歌曲，避免再让用户重新挑歌。
  if (state.playerSong) {
    goHome();
  } else {
    showLearnLibrary();
  }
}

export function bindLearn() {
  document.querySelectorAll("[data-enter-learn]").forEach((btn) => {
    btn.onclick = () => {
      if (state.currentPage !== "player") api.showPage("player");
      enterLearn();
    };
  });
  $("learnBack").onclick = () => {
    if ($("learnLibrary").hidden && $("learnHome").hidden) {
      if (!state.playerSong) {
        showLearnLibrary();
        return;
      }
      goHome();
      return;
    }
    if ($("learnLibrary").hidden) {
      showLearnLibrary();
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
    onBook: () => openStudyBook()
  });
  const songSearch = $("learnSongSearch");
  const songSearchClear = $("learnSongSearchClear");
  if (songSearch) {
    let timer = 0;
    const run = () => {
      const query = songSearch.value.trim();
      if (songSearchClear) songSearchClear.hidden = !query;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => loadLearnLibrary(query), query ? 180 : 0);
    };
    songSearch.addEventListener("input", run);
    songSearch.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        run();
        songSearch.blur();
      }
    });
    if (songSearchClear) {
      songSearchClear.onclick = () => {
        songSearch.value = "";
        run();
        songSearch.focus();
      };
    }
  }
  const mistakesBtn = $("learnMistakesBtn");
  const wordsBtn = $("learnWordsBtn");
  const openBookFromLibrary = async () => {
    if (state.playerSong && state.playerSong.status === "ready") return openStudyBook("mistakes");
    const response = await fetchJson("/api/songs", { cache: "no-store" }).catch(() => null);
    const song =
      response && response.ok && response.data && (response.data.songs || []).find((item) => item.status === "ready");
    if (!song) return showToast(t("learn.noAddedSongs"));
    await selectLearnSong(song.id);
    if (state.playerSong && state.playerSong.id === song.id) openStudyBook("mistakes");
  };
  if (mistakesBtn) mistakesBtn.onclick = openBookFromLibrary;
  if (wordsBtn)
    wordsBtn.onclick = async () => {
      if (state.playerSong && state.playerSong.status === "ready") return openStudyBook("words");
      if (getStudyWords().length) return openStudyBook("words");
      const response = await fetchJson("/api/songs", { cache: "no-store" }).catch(() => null);
      const song =
        response && response.ok && response.data && (response.data.songs || []).find((item) => item.status === "ready");
      if (!song) return showToast(t("learn.noAddedSongs"));
      await selectLearnSong(song.id);
      if (state.playerSong && state.playerSong.id === song.id) openStudyBook("words");
    };
  const bookGo = $("learnBookGo");
  if (bookGo) bookGo.onclick = () => startReview();
  const saveRetry = $("learnSaveRetry");
  if (saveRetry) {
    saveRetry.onclick = async () => {
      if (!ui.pendingScore || !ui.run) return;
      ui.attemptId =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : String(Date.now()) + "-" + String(Math.random());
      saveRetry.disabled = true;
      const ok = await submitRun(ui.pendingScore);
      saveRetry.disabled = false;
      if (ok) {
        saveRetry.hidden = true;
        showScore(ui.pendingScore);
      }
    };
  }
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
      if (ui.run.review) return openStudyBook();
      return goHome();
    }
    startMode(nextMode(ui.mode));
  };
  $("learnDone").onclick = () => exitLearn();
}
