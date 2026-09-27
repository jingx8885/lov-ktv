import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { songArtist, songTitle } from "../../../../shared/ui/js/song.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { applyPlayerVocalMix, pausePlayer, unlockPlayerGesture } from "../playback/controls.js";
import { kickPlayerPaint } from "../playback/lyrics.js";
import { applyLearnRate, cancelCueWindow, loadLearnDiff, resetLearnRate, setLearnDiff } from "./play.js";
import { cancelCountdown, celebrateCorrect, clearLearnFx } from "./fx.js";
import { bindQuiz, runQuiz, startQuiz, stopQuiz, quizScoreView, syncQuizLyricMode } from "./quiz.js";
import { bindTap, runTap, startTap, stopTap, syncTapLyricMode, tapScoreView } from "./tap.js";
import { bindEcho, runEcho, startEcho, stopEcho, echoScoreView } from "./echo.js";
import { bindCampaign, currentCampaign, firstReady, loadCampaign, paintCampaign, setCampaign } from "./campaign.js";
import { bindLesson, lessonScoreView, runLesson, startLesson, stopLesson } from "./lesson.js";
import { RECITE_PANES, bindRecite, openRecite, reciteBack, reciteSongId, stopRecite } from "./recite.js";
import { WORDS_PANES, bindSongWords, openSongWords, stopSongWords } from "./words.js";
import { getStudyWords } from "../../../desk/js/lyrics.js";

export { openRecite } from "./recite.js";
export { openSongWords } from "./words.js";

/** @type {{ mode: LearnMode | "lesson" | "", pack: LearnQuiz | null, vocalWas: number, boot: number, generation: number, run: { unitId: string, skill: string, review?: boolean } | null, lesson: any, attemptId: string, pendingScore: any, result: any, standalone: boolean }} */
const ui = {
  mode: "",
  pack: null,
  vocalWas: 1,
  boot: 0,
  generation: 0,
  run: null,
  lesson: null,
  attemptId: "",
  pendingScore: null,
  // The saved result of the last campaign run, plus what it changed on the path.
  result: null,
  standalone: false
};
let libraryLoad = 0;
let songSelectionLoad = 0;
let pendingSongId = "";
let pendingSkillKey = "";
let pendingMode = "";
let modeLoad = 0;

/** @type {Record<string, { pane: string, setup: (pack: LearnQuiz) => any, run: () => Promise<any>, stop: () => void, score: (score: any, grade: (pct: number) => string) => LearnScoreView }>} */
const MODES = {
  quiz: { pane: "learnQuiz", setup: startQuiz, run: runQuiz, stop: stopQuiz, score: quizScoreView },
  tap: { pane: "learnTap", setup: startTap, run: runTap, stop: stopTap, score: tapScoreView },
  echo: { pane: "learnEcho", setup: startEcho, run: runEcho, stop: stopEcho, score: echoScoreView }
};
const CYCLE = ["quiz", "tap"];
const PANES = [
  "learnLibrary",
  "learnHome",
  "learnQuiz",
  "learnTap",
  "learnEcho",
  "learnScore",
  "learnLesson",
  "learnBook",
  ...WORDS_PANES,
  ...RECITE_PANES
];
/** Panes that own the whole screen — the lyric strip has nothing to show under them. */
const NO_LYRIC_PANES = new Set([
  "learnLibrary",
  "learnHome",
  "learnScore",
  "learnBook",
  ...WORDS_PANES,
  ...RECITE_PANES
]);

function showPane(id) {
  PANES.forEach((name) => {
    const el = $(name);
    if (el) el.hidden = name !== id;
  });
  const lyric = $("learnLyricMode");
  if (lyric) lyric.hidden = NO_LYRIC_PANES.has(id);
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

export function syncLearnLyricMode() {
  if (!isLearnOpen()) return;
  if ($("learnTap") && !$("learnTap").hidden) syncTapLyricMode();
  if ($("learnQuiz") && !$("learnQuiz").hidden) syncQuizLyricMode();
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
  stopRecite();
  stopSongWords();
  cancelCueWindow();
}

export function exitLearn() {
  if (!isLearnOpen()) return;
  songSelectionLoad += 1;
  pendingSongId = "";
  pendingSkillKey = "";
  pendingMode = "";
  modeLoad += 1;
  paintSongSelection();
  paintModeSelection();
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
  ui.result = null;
  ui.standalone = false;
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

const DAILY_GOAL = 1;
const DAILY_KEY = "lovktv.learn.daily.v1";

function dayKey(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function readDaily() {
  try {
    const raw = JSON.parse(localStorage.getItem(DAILY_KEY) || "{}");
    return raw && raw.days && typeof raw.days === "object" ? raw : { days: {} };
  } catch (_) {
    return { days: {} };
  }
}

function dailySnapshot() {
  const data = readDaily();
  const today = dayKey();
  const days = data.days || {};
  let streak = 0;
  const cursor = new Date();
  // A streak counts backwards from today; if today is not done yet, keep the
  // chain alive from yesterday so the banner feels encouraging before practice.
  if (!Number(days[today])) cursor.setDate(cursor.getDate() - 1);
  while (Number(days[dayKey(cursor)]) > 0) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return { count: Number(days[today] || 0), streak };
}

function paintDailyGoal() {
  const el = $("learnDailyGoal");
  if (!el) return;
  const snap = dailySnapshot();
  const done = snap.count >= DAILY_GOAL;
  el.classList.toggle("is-done", done);
  el.textContent = done
    ? t("learn.daily.done", { streak: Math.max(1, snap.streak) })
    : t("learn.daily.goal", { done: snap.count, goal: DAILY_GOAL, streak: snap.streak });
}

/** @returns {boolean} true on the run that reaches today's goal */
function markDailyPractice() {
  const data = readDaily();
  const today = dayKey();
  data.days[today] = Number(data.days[today] || 0) + 1;
  // Keep local state tiny while retaining enough history for a useful streak.
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 120);
  Object.keys(data.days).forEach((key) => {
    if (key < dayKey(cutoff)) delete data.days[key];
  });
  try {
    localStorage.setItem(DAILY_KEY, JSON.stringify(data));
  } catch (_) {}
  paintDailyGoal();
  return data.days[today] === DAILY_GOAL;
}

/** Count a finished run toward the daily goal and cheer the run that completes it. */
function noteDailyPractice() {
  if (markDailyPractice()) showToast(t("learn.daily.done", { streak: Math.max(1, dailySnapshot().streak) }));
}

/** 歌曲专属背词入口的副标题。没挑过词时提示先挑词，挑过之后报进度，
 *  免得用户点进去才知道今天没有要背的。 */
let songWordsLoad = 0;

async function paintSongWordsCard() {
  const meta = $("learnSongWordsMeta");
  const song = state.playerSong;
  if (!meta || !song) return;
  const loadId = ++songWordsLoad;
  const { ok, data } = await fetchJson(`/api/learn/deck?deck=word&cards=0&song_id=${encodeURIComponent(song.id)}`, {
    cache: "no-store"
  }).catch(() => ({ ok: false, data: null }));
  if (loadId !== songWordsLoad || !ok || !data) return;
  if (!state.playerSong || state.playerSong.id !== song.id) return;
  const total = Number(data.total || 0);
  if (!total) {
    meta.textContent = t("learn.songWordsSetupMeta");
    return;
  }
  const kept = Number(data.new || 0) + Number(data.learning || 0);
  meta.textContent = t("learn.songWordsMeta", { kept, due: Number(data.due || 0) });
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
  ui.result = null;
  showPane("learnHome");
  paintSongHead();
  paintDailyGoal();
  paintSongWordsCard();
  paintDiff();
  loadCampaign(true).then((data) => {
    if (data) paintCampaign(data);
  });
}

function campaignProgress(data) {
  const goal = data && data.goal;
  if (!goal) return { pct: 0, done: false };
  const slices = [goal.words, goal.sentences, goal.read].filter(Boolean);
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
        <span class="learn-song-copy"><b>${escapeHtml(songTitle(song))}</b><small>${escapeHtml(songArtist(song) || t("common.unknownArtist"))}</small><span class="learn-song-status" role="status" hidden></span></span>
        <span class="learn-song-progress"><i style="--pct:${progress.pct}%"></i><em>${progress.done ? escapeHtml(t("learn.completed")) : `${progress.pct}%`}</em></span>
      </button>`;
    })
    .join("");
  paintSongSelection();
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

function paintSongSelection() {
  $("learnSongList")
    ?.querySelectorAll("[data-learn-song]")
    .forEach((btn) => {
      const loading = btn.dataset.learnSong === pendingSongId;
      btn.disabled = loading;
      btn.classList.toggle("is-loading", loading);
      btn.setAttribute("aria-busy", String(loading));
      const status = btn.querySelector(".learn-song-status");
      if (status) {
        status.hidden = !loading;
        status.textContent = loading ? t("learn.loadingSong") : "";
      }
    });
}

async function selectLearnSong(songId) {
  if (!songId || !api.loadPlayerSong || pendingSongId === songId) return;
  const selectionLoad = ++songSelectionLoad;
  pendingSongId = songId;
  paintSongSelection();
  ui.pack = null;
  setCampaign(null);
  syncLearnNav(true);
  try {
    await api.loadPlayerSong(songId, { play: false });
    if (selectionLoad !== songSelectionLoad || !isLearnOpen()) return;
    if (!state.playerSong || state.playerSong.id !== songId) {
      showToast(t("common.loadFailed"));
      return;
    }
    // Audio and lyrics may need downloading; keep feedback on the visible
    // library until the player finishes, then show campaign loading in place.
    // Campaign data remains authoritative if the media lyrics request failed.
    showPane("learnHome");
    paintSongHead();
    paintDailyGoal();
    paintSongWordsCard();
    paintCampaign(null);
    const data = await loadCampaign(true);
    if (selectionLoad !== songSelectionLoad || !state.playerSong || state.playerSong.id !== songId || !isLearnOpen())
      return;
    paintCampaign(data || null);
  } catch (err) {
    if (selectionLoad === songSelectionLoad && isLearnOpen()) showToast(t("common.loadFailed"));
  } finally {
    if (selectionLoad === songSelectionLoad) {
      pendingSongId = "";
      paintSongSelection();
    }
  }
}

function showLearnLibrary() {
  songSelectionLoad += 1;
  pendingSongId = "";
  pendingSkillKey = "";
  pendingMode = "";
  modeLoad += 1;
  paintModeSelection();
  stopModes();
  restoreVocal();
  resetLearnRate();
  ui.mode = "";
  ui.pack = null;
  ui.run = null;
  ui.lesson = null;
  ui.result = null;
  showPane("learnLibrary");
  $("topTitle").textContent = t("learn.pageTitle");
  $("learnTitle").textContent = t("learn.pageTitle");
  $("learnMeta").textContent = "";
  if ($("learnSongSearch")) $("learnSongSearch").value = "";
  if ($("learnSongSearchClear")) $("learnSongSearchClear").hidden = true;
  loadLearnLibrary();
}

/** How far a campaign reaches: units with an open skill, and whether every skill is passed. */
function pathState(pack) {
  const units = (pack && pack.units) || [];
  const passed = (skill) => skill.status === "passed" || skill.status === "mastered";
  return {
    open: units.filter((unit) => (unit.skills || []).some((skill) => skill.status !== "locked")).length,
    done: units.length > 0 && units.every((unit) => (unit.skills || []).every(passed))
  };
}

/** Fewest extra right answers that lift `ok` of `total` to the pass line. */
function answersToPass(ok, total, pass) {
  for (let n = 1; ok + n <= total; n += 1) {
    if (Math.round(((ok + n) * 100) / total) >= pass) return n;
  }
  return 0;
}

/**
 * One line that says what the run changed: how close a miss came to passing,
 * or what the pass unlocked. Free play saves nothing, so it gets none.
 * @param {any} score
 * @returns {{ text: string, tone: string, big?: boolean } | null}
 */
function runBadge(score) {
  const result = ui.result;
  if (!ui.run || ui.standalone || !result) return null;
  if (ui.run.review) {
    const left = Number(result.mistakes || 0);
    if (!left) return { text: t("learn.badge.bookDone"), tone: "unlock", big: true };
    const cleared = Math.max(0, Number(result.mistakes_before || 0) - left);
    return cleared ? { text: t("learn.badge.bookCleared", { n: cleared, left }), tone: "pass" } : null;
  }
  const pass = Number(result.pass_pct) || 70;
  const pct = Number(result.pct != null ? result.pct : score.pct) || 0;
  if (!result.passed) {
    // Read runs score hits on the tap board, not items, so only a percentage fits.
    const need = ui.mode === "lesson" ? answersToPass(score.ok || 0, score.total || 0, pass) : 0;
    return {
      text: need ? t("learn.badge.need", { n: need }) : t("learn.badge.needPct", { n: Math.max(1, pass - pct) }),
      tone: "miss"
    };
  }
  if (result.pathDone) return { text: t("learn.badge.allClear"), tone: "unlock", big: true };
  if (result.unlocked) return { text: t("learn.badge.unlock", { n: result.unlocked }), tone: "unlock", big: true };
  if (pct >= 90) return { text: t("learn.badge.mastered"), tone: "gold" };
  return { text: t("learn.badge.passed"), tone: "pass" };
}

function paintBadge(badge) {
  const el = $("learnScoreBadge");
  if (!el) return;
  el.hidden = !badge;
  el.className = `learn-score-badge${badge ? ` is-${badge.tone}` : ""}`;
  el.textContent = badge ? badge.text : "";
}

function paintStars(pct) {
  const el = $("learnScoreStars");
  if (!el) return;
  // A cover score is a loose loudness-and-timing estimate; stars would overstate it.
  el.hidden = ui.mode === "echo";
  if (el.hidden) return;
  const pass = (ui.result && Number(ui.result.pass_pct)) || 70;
  const n = pct >= 100 ? 3 : pct >= 90 ? 2 : pct >= pass ? 1 : 0;
  el.setAttribute("aria-label", t("learn.stars", { n }));
  el.innerHTML = [0, 1, 2]
    .map((i) => `<i class="learn-star${i < n ? " is-on" : ""}" style="--i:${i}" aria-hidden="true">★</i>`)
    .join("");
}

/** @param {LearnScoreView["stats"]} stats */
function paintStats(stats) {
  const el = $("learnScoreStats");
  if (!el) return;
  const rows = stats || [];
  el.hidden = !rows.length;
  el.innerHTML = rows
    .map((row) => `<li><b>${escapeHtml(row.value)}</b><span>${escapeHtml(row.label)}</span></li>`)
    .join("");
}

/** After a passed stage, offer the next open one so the path keeps moving. */
function paintNextStep() {
  const btn = $("learnNext");
  if (!btn) return null;
  const run = ui.run;
  const result = ui.result;
  const ready = run && !run.review && !ui.standalone && result && result.passed ? firstReady(result.campaign) : null;
  const step = ready && !(ready.unit.id === run.unitId && ready.skill.id === run.skill) ? ready : null;
  btn.hidden = !step;
  btn.disabled = false;
  if (!step) return null;
  btn.textContent = t("learn.nextStep", {
    step: `${t("learn.unit", { n: step.unit.index + 1 })} · ${t("learn.skill." + step.skill.id)}`
  });
  btn.onclick = () => {
    $("learnMix").pause();
    btn.disabled = true;
    startSkill(step.unit.id, step.skill.id).finally(() => {
      btn.disabled = false;
    });
  };
  return step;
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
  const badge = runBadge(score);
  paintBadge(badge);
  paintStars(Number(score.pct) || 0);
  paintStats(view.stats);
  // The next stage takes the primary slot; otherwise replaying is the main action.
  $("learnAgain").classList.toggle("primary", !paintNextStep());
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
  if (badge && badge.big) celebrateCorrect($("learnScoreBadge"), { line: true, combo: 5 });
  else if (view.celebrate) celebrateCorrect($("learnScoreNum"), { line: true });
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

function newAttemptId() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : String(Date.now()) + "-" + String(Math.random());
}

async function submitRun(score) {
  const run = ui.run;
  const song = state.playerSong;
  if (!run || !song) return false;
  // Compare the path before and after, so the score screen can tell a fresh
  // unlock from a replay of a stage that was already open.
  const prev = currentCampaign();
  const before = prev && prev.song_id === song.id ? pathState(prev) : null;
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
    const after = data && data.campaign ? pathState(data.campaign) : null;
    ui.result = Object.assign({}, data, {
      unlocked: before && after && after.open > before.open ? after.open : 0,
      pathDone: !!(before && after && after.done && !before.done)
    });
  }
  return ok;
}

async function startMode(mode, pack) {
  const spec = MODES[mode] || MODES.quiz;
  const modeName = MODES[mode] ? mode : "quiz";
  const generation = ui.generation;
  const loadId = ++modeLoad;
  pendingMode = modeName;
  paintModeSelection();
  let loaded;
  try {
    loaded = pack || (await loadPack());
  } finally {
    if (loadId === modeLoad) {
      pendingMode = "";
      paintModeSelection();
    }
  }
  if (!loaded || generation !== ui.generation || !isLearnOpen()) return;
  stopModes();
  const boot = ui.boot;
  applyLearnRate();
  unlockPlayerGesture();
  pausePlayer();
  ui.mode = /** @type {LearnMode} */ (MODES[mode] ? mode : "quiz");
  ui.attemptId = newAttemptId();
  ui.pendingScore = null;
  ui.result = null;
  showPane(spec.pane);
  spec.setup(loaded);
  if (boot !== ui.boot || ui.mode !== mode) return;
  const score = await spec.run();
  if (boot !== ui.boot || generation !== ui.generation || !isLearnOpen()) return;
  if (score) {
    noteDailyPractice();
    if (ui.run && !ui.standalone) await submitRun(score);
    if (boot !== ui.boot || generation !== ui.generation || !isLearnOpen()) return;
    showScore(score);
  }
}

async function startSkill(unitId, skill) {
  const song = state.playerSong;
  if (!song || pendingSkillKey) return;
  const generation = ui.generation;
  const key = `${unitId}:${skill}`;
  pendingSkillKey = key;
  paintSkillSelection();
  try {
    const { ok, status, data } = await fetchJson(
      `/api/songs/${song.id}/learn/lesson?unit=${encodeURIComponent(unitId)}&skill=${encodeURIComponent(skill)}`
    );
    if (!ok || generation !== ui.generation || !isLearnOpen()) {
      if (!ok) showToast((data && data.detail) || (status === 409 ? t("learn.cant") : t("learn.loadFail")));
      return;
    }
    ui.run = { unitId, skill };
    ui.lesson = data;
    if (data.play_mode === "tap") {
      const pack = await loadPack();
      if (!pack || generation !== ui.generation || !isLearnOpen()) return;
      return startMode(data.play_mode, scopedPack(data.lines || pack.lines));
    }
    await startLessonRun(data);
  } finally {
    if (pendingSkillKey === key) {
      pendingSkillKey = "";
      paintSkillSelection();
    }
  }
}

function paintModeSelection() {
  document.querySelectorAll("[data-learn-mode]").forEach((btn) => {
    const loading = !!pendingMode && btn.dataset.learnMode === pendingMode;
    btn.disabled = !!pendingMode;
    btn.classList.toggle("is-loading", loading);
    btn.setAttribute("aria-busy", String(loading));
    if (loading) btn.setAttribute("aria-label", t("common.loading"));
    else btn.removeAttribute("aria-label");
  });
}

function paintSkillSelection() {
  document.querySelectorAll("#learnPath [data-skill]").forEach((btn) => {
    const loading = `${btn.dataset.unit}:${btn.dataset.skill}` === pendingSkillKey;
    btn.disabled = loading;
    btn.classList.toggle("is-loading", loading);
    btn.setAttribute("aria-busy", String(loading));
    if (loading) btn.setAttribute("aria-label", t("common.loading"));
    else btn.setAttribute("aria-label", btn.dataset.label || "");
  });
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
  ui.attemptId = newAttemptId();
  ui.pendingScore = null;
  ui.result = null;
  showPane("learnLesson");
  startLesson(lesson);
  if (boot !== ui.boot || generation !== ui.generation || ui.mode !== "lesson" || !isLearnOpen()) return;
  const score = await runLesson();
  if (boot !== ui.boot || generation !== ui.generation || !isLearnOpen()) return;
  if (score) {
    noteDailyPractice();
    await submitRun(score);
    if (boot !== ui.boot || generation !== ui.generation || !isLearnOpen()) return;
    showScore(score);
  }
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
  ui.standalone = false;
  openLearnShell();
  // 从听歌页进入时直接打开当前歌曲，避免再让用户重新挑歌。
  if (state.playerSong) {
    goHome();
  } else {
    showLearnLibrary();
  }
}

export async function enterCover() {
  if (!state.playerSong) return showToast(t("learn.noSong"));
  ui.standalone = true;
  openLearnShell();
  await startMode("echo");
}

function shown(el) {
  return !!el && !el.disabled && el.getClientRects().length > 0;
}

/**
 * With a keyboard, 1–9 pick a choice and Enter moves past a miss. A focused
 * button keeps its own Enter, and typing in a field or an open sheet wins.
 */
function bindLearnKeys() {
  document.addEventListener("keydown", (event) => {
    if (!isLearnOpen() || event.repeat || event.altKey || event.ctrlKey || event.metaKey) return;
    const target = /** @type {HTMLElement} */ (event.target);
    if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;
    if (document.querySelector(".overlay:not([hidden])")) return;
    const pane = document.querySelector("#playerLearn .learn-body:not([hidden])");
    if (!pane) return;
    if (/^[1-9]$/.test(event.key)) {
      const choices = Array.from(pane.querySelectorAll(".learn-choice")).filter(shown);
      const btn = choices[Number(event.key) - 1];
      if (!btn) return;
      event.preventDefault();
      // detail 0 marks a pointerless click, which onPress answers.
      btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      return;
    }
    if (event.key !== "Enter" || (target && target.closest && target.closest("button, a"))) return;
    const next = Array.from(pane.querySelectorAll(".learn-next, #reciteDetailNext")).find(shown);
    if (!next) return;
    event.preventDefault();
    /** @type {HTMLElement} */ (next).click();
  });
}

export function bindLearn() {
  const cover = $("playerEchoBtn");
  if (cover) cover.onclick = () => enterCover();
  document.querySelectorAll("[data-enter-learn]").forEach((btn) => {
    btn.onclick = () => {
      if (state.currentPage !== "player") api.showPage("player");
      enterLearn();
    };
  });
  $("learnBack").onclick = () => {
    // 背诵牌组自己消化一层返回：卡片流 / 结算 → 牌组首页。
    if (reciteBack()) return;
    if ($("learnRecite") && !$("learnRecite").hidden) {
      // 歌曲专属牌组是从学习首页进来的，回到那首歌，不要甩回学习中心。
      const songId = reciteSongId();
      stopRecite();
      if (songId && state.playerSong && state.playerSong.id === songId) goHome();
      else showLearnLibrary();
      return;
    }
    if ($("learnWords") && !$("learnWords").hidden) {
      stopSongWords();
      if (state.playerSong) goHome();
      else showLearnLibrary();
      return;
    }
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
  bindLearnKeys();
  bindCampaign({
    onSkill: (unitId, skill) => startSkill(unitId, skill),
    onBook: () => openStudyBook()
  });
  const learnHead = {
    showPane,
    setHead: (title, meta) => {
      $("learnTitle").textContent = title;
      $("learnMeta").textContent = meta || "";
    }
  };
  bindRecite(learnHead);
  bindSongWords(learnHead);
  const songWordsBtn = $("learnSongWordsBtn");
  if (songWordsBtn) songWordsBtn.onclick = () => openSongWords();
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
  // 牌组是跨歌的，不该再逼用户先挑一首歌。
  if (mistakesBtn) mistakesBtn.onclick = () => openRecite("mistake");
  if (wordsBtn) wordsBtn.onclick = () => openRecite("word");
  const bookGo = $("learnBookGo");
  if (bookGo) bookGo.onclick = () => startReview();
  const saveRetry = $("learnSaveRetry");
  if (saveRetry) {
    saveRetry.onclick = async () => {
      const score = ui.pendingScore;
      if (!score || !ui.run) return;
      const generation = ui.generation;
      // The server claims an attempt id before it validates, so a retry needs a fresh one.
      ui.attemptId = newAttemptId();
      saveRetry.disabled = true;
      const ok = await submitRun(score);
      saveRetry.disabled = false;
      if (ok && generation === ui.generation && isLearnOpen()) showScore(score);
    };
  }
  $("learnAgain").onclick = () => {
    $("learnMix").pause();
    if (ui.run && ui.run.review) return startReview();
    if (ui.run && ui.mode === "lesson") return startSkill(ui.run.unitId, ui.run.skill);
    if (ui.run && ui.mode === "tap") return startSkill(ui.run.unitId, ui.run.skill);
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
