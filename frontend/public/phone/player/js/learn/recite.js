import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { songTitle } from "../../../../shared/ui/js/song.js";
import { state } from "../../../state.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { showToast } from "../../../ui/js/toast.js";
import { celebrateCorrect, playMissSfx } from "./fx.js";
import { mediaUrl } from "../playback/media.js";
import { getStudyWords } from "../../../desk/js/lyrics.js";

export const RECITE_PANES = ["learnRecite", "learnReciteRun", "learnReciteDone"];

/** Padding around a token's cue window. A single word is ~250ms — too short to
 *  recognise on its own, so the snippet opens a beat early and closes a beat late. */
const LEAD_MS = 400;
const MIN_SNIPPET_MS = 1200;
/** A card the user keeps missing would otherwise loop the round forever. */
const MAX_REDRILL = 3;

/** @type {{ showPane: (id: string) => void, setHead: (title: string, meta: string) => void }} */
let hooks = { showPane: () => {}, setHead: () => {} };

/** @type {{ deck: string, songId: string, songTitle: string, size: number, summary: any, cards: any[], loading: boolean, gen: number }} */
const view = {
  deck: "word",
  songId: "",
  songTitle: "",
  size: 0,
  summary: null,
  cards: [],
  loading: false,
  gen: 0
};

/** @type {{ deck: string, songId: string, queue: any[], pos: number, total: number, verdict: Map<string, boolean>, tries: Map<string, number>, locked: boolean, gen: number, active: boolean }} */
const run = {
  deck: "",
  songId: "",
  queue: [],
  pos: 0,
  total: 0,
  verdict: new Map(),
  tries: new Map(),
  locked: false,
  gen: 0,
  active: false
};

const audio = { stopAt: 0, timer: 0, btn: /** @type {HTMLElement | null} */ (null) };
let imported = false;

/* ------------------------------------------------------------------ audio */

/**
 * The deck is cross-song, so it cannot ride `playCueWindow()` — that one is
 * bound to `#playerAudio` and only knows the currently loaded song.
 */
function reciteAudio() {
  const el = /** @type {HTMLAudioElement | null} */ ($("reciteAudio"));
  if (el && !el.dataset.reciteBound) {
    el.dataset.reciteBound = "1";
    el.addEventListener("timeupdate", () => {
      if (audio.stopAt && el.currentTime >= audio.stopAt) stopSnippet();
    });
    el.addEventListener("ended", () => stopSnippet());
  }
  return el;
}

function stopSnippet() {
  const el = /** @type {HTMLAudioElement | null} */ ($("reciteAudio"));
  if (el) {
    try {
      el.pause();
    } catch (err) {}
  }
  if (audio.timer) window.clearTimeout(audio.timer);
  audio.timer = 0;
  audio.stopAt = 0;
  if (audio.btn) audio.btn.classList.remove("is-playing");
  audio.btn = null;
}

function hasSnippet(detail) {
  return !!(detail && detail.song_id && Number(detail.end_ms || 0) > Number(detail.start_ms || 0));
}

/** @param {any} detail @param {HTMLElement | null} [btn] */
function playSnippet(detail, btn) {
  const el = reciteAudio();
  if (!el || !hasSnippet(detail)) return;
  const startMs = Math.max(0, Number(detail.start_ms || 0) - LEAD_MS);
  const endMs = Math.max(startMs + MIN_SNIPPET_MS, Number(detail.end_ms || 0) + LEAD_MS);
  const url = mediaUrl(detail.song_id, "original.mp3");
  stopSnippet();
  if (el.getAttribute("data-recite-src") !== url) {
    el.setAttribute("data-recite-src", url);
    // 标签上写的是 preload="none"（别让整首歌在进牌组时就开始拉），可那样赋 src 不会
    // 触发加载，`loadedmetadata` 永远不来、下面的 play() 也就永远不会跑。真要出声这一刻
    // 才抬到 metadata。
    el.preload = "metadata";
    el.src = url;
  }
  audio.stopAt = endMs / 1000;
  audio.btn = btn || null;
  if (audio.btn) audio.btn.classList.add("is-playing");
  const go = () => {
    try {
      el.currentTime = startMs / 1000;
    } catch (err) {}
    el.play().catch(() => {});
  };
  if (el.readyState >= 1) go();
  else el.addEventListener("loadedmetadata", go, { once: true });
  // Belt and braces: `timeupdate` stops firing if the file never loads.
  audio.timer = window.setTimeout(stopSnippet, endMs - startMs + 900);
}

/* ------------------------------------------------------------- deck home */

function deckTitle(deck) {
  if (deck === "mistake") return t("learn.recite.mistakeTitle");
  // 歌曲专属牌组顶栏点名这首歌，免得跟跨歌牌组看起来一模一样。
  return view.songId ? t("learn.recite.songTitle") : t("learn.recite.wordTitle");
}

function paintHead() {
  hooks.setHead(deckTitle(view.deck), view.songId ? view.songTitle : "");
}

/** 歌曲范围只在词牌组有意义；错题本仍是跨歌的。 */
function scopeQuery(deck, songId) {
  return deck === "word" && songId ? `&song_id=${encodeURIComponent(songId)}` : "";
}

function statCell(value, label, tone) {
  const zero = !value ? " is-zero" : "";
  return `<div class="recite-stat${tone ? " " + tone : ""}${zero}"><b>${value}</b><small>${escapeHtml(label)}</small></div>`;
}

function boxBadge(card, now) {
  if (card.skipped) return { cls: "is-skipped", text: t("learn.recite.statSkipped") };
  if (card.retired) return { cls: "is-mastered", text: t("learn.recite.boxMastered") };
  if (!card.reps) return { cls: "is-new", text: t("learn.recite.boxNew") };
  if (Number(card.due_at || 0) <= now) return { cls: "is-due", text: t("learn.recite.boxDue") };
  return { cls: "", text: t("learn.recite.boxStage", { n: Number(card.stage || 0) + 1 }) };
}

function paintList() {
  const list = $("reciteList");
  if (!list) return;
  const cards = view.cards || [];
  if (!cards.length) {
    list.innerHTML = "";
    return;
  }
  const now = Date.now();
  const removable = view.deck === "word";
  list.innerHTML =
    `<div class="recite-list-h"><b>${escapeHtml(t("learn.recite.listTitle"))}</b><span>${escapeHtml(
      t("learn.recite.listCount", { n: cards.length })
    )}</span></div>` +
    cards
      .map((card) => {
        const badge = boxBadge(card, now);
        const sub = card.zh || card.romaji || card.song_title || "";
        // 砍掉的词换成「恢复」：砍词是可逆状态，不是删除。
        const action = !removable
          ? `<span></span>`
          : card.skipped
            ? `<button class="recite-restore" type="button" data-restore="${escapeHtml(
                card.card_id
              )}" aria-label="${escapeHtml(t("learn.recite.restore"))}">${escapeHtml(
                t("learn.recite.restore")
              )}</button>`
            : `<button class="recite-drop" type="button" data-drop="${escapeHtml(card.card_id)}" title="${escapeHtml(
                t("learn.recite.remove")
              )}" aria-label="${escapeHtml(t("learn.recite.remove"))}">×</button>`;
        return `<div class="recite-item${card.skipped ? " is-skipped" : ""}">
          <span class="recite-item-copy"><b>${escapeHtml(card.text || "")}</b><span>${escapeHtml(sub)}</span></span>
          <span class="recite-box ${badge.cls}">${escapeHtml(badge.text)}</span>
          ${action}
        </div>`;
      })
      .join("");
  list.querySelectorAll("[data-drop]").forEach((btn) => {
    btn.addEventListener("click", () => dropCard(btn.getAttribute("data-drop") || ""));
  });
  list.querySelectorAll("[data-restore]").forEach((btn) => {
    btn.addEventListener("click", () => restoreCard(btn.getAttribute("data-restore") || ""));
  });
}

function paintSizes() {
  const box = $("reciteSizes");
  if (!box) return;
  const sizes = (view.summary && view.summary.sizes) || [10, 20, 30];
  if (!view.size) view.size = Number(sizes[0]) || 10;
  box.innerHTML = sizes
    .map(
      (size) =>
        `<button type="button" role="radio" data-size="${size}" aria-checked="${
          size === view.size ? "true" : "false"
        }" class="${size === view.size ? "on" : ""}">${escapeHtml(t("learn.recite.sizeN", { n: size }))}</button>`
    )
    .join("");
  box.querySelectorAll("[data-size]").forEach((btn) => {
    btn.addEventListener("click", () => {
      view.size = Number(btn.getAttribute("data-size")) || view.size;
      paintSizes();
      paintStart();
    });
  });
}

function paintStart() {
  const btn = /** @type {HTMLButtonElement | null} */ ($("reciteStart"));
  if (!btn) return;
  const due = Number((view.summary && view.summary.due) || 0);
  btn.disabled = !due;
  btn.textContent = due
    ? t("learn.recite.start", { n: Math.min(due, view.size || 10) })
    : t("learn.recite.startDone");
}

function paintDeck() {
  const summary = view.summary;
  const lead = $("reciteLead");
  const stats = $("reciteStats");
  const empty = $("reciteEmpty");
  const sizes = $("reciteSizes");
  const start = $("reciteStart");
  if (!summary) {
    if (lead) lead.textContent = t("common.loading");
    if (stats) stats.innerHTML = "";
    if (empty) empty.hidden = true;
    if (sizes) sizes.hidden = true;
    if (start) start.hidden = true;
    paintList();
    return;
  }
  const bare = !Number(summary.total || 0);
  if (lead) {
    lead.textContent = summary.streak
      ? t("learn.recite.streak", { n: summary.streak })
      : summary.today
        ? t("learn.recite.todayDone", { n: summary.today })
        : t("learn.recite.streakNone");
  }
  const setAside = Number(summary.skipped || 0);
  if (stats) {
    stats.hidden = bare;
    stats.classList.toggle("has-skipped", !!setAside);
    stats.innerHTML = bare
      ? ""
      : statCell(summary.due, t("learn.recite.statDue"), "is-due") +
        statCell(summary.new, t("learn.recite.statNew"), "") +
        statCell(summary.learning, t("learn.recite.statLearning"), "") +
        statCell(summary.mastered, t("learn.recite.statMastered"), "") +
        (setAside ? statCell(setAside, t("learn.recite.statSkipped"), "") : "");
  }
  // 队列空掉有两种，别混成一句话：词真的全背熟了（mastered 覆盖了在背的词），
  // 还是只是今天该背的都背完、明天到期再来。后者说「背完了」是在骗人。
  const learnable = Number(summary.new || 0) + Number(summary.learning || 0);
  const idle = !bare && !Number(summary.due || 0) && !!view.songId;
  const allMastered = idle && !learnable;
  if (empty) {
    empty.hidden = !bare && !idle;
    const title = $("reciteEmptyTitle");
    const hint = $("reciteEmptyHint");
    if (title)
      title.textContent = allMastered
        ? t("learn.recite.allDone")
        : idle
          ? t("learn.recite.dayClear")
          : view.deck === "mistake"
            ? t("learn.recite.emptyMistake")
            : t("learn.recite.emptyWord");
    if (hint)
      hint.textContent = allMastered
        ? t("learn.recite.allDoneHint")
        : idle
          ? t("learn.recite.dayClearHint")
          : view.deck === "mistake"
            ? t("learn.recite.emptyMistakeHint")
            : t("learn.recite.emptyWordHint");
  }
  if (sizes) sizes.hidden = bare || idle;
  if (start) start.hidden = bare || idle;
  if (!bare && !idle) {
    paintSizes();
    paintStart();
  }
  paintList();
}

/** Move the browser's old localStorage word list to the server, once per load. */
async function importLocalWords() {
  if (imported || view.deck !== "word") return;
  imported = true;
  const words = getStudyWords();
  if (!words.length) return;
  const cards = words.map((word) => ({
    song_id: word.song_id || "",
    song_title: word.song || "",
    item_key: word.key || word.text || "",
    text: word.text || "",
    zh: word.zh || "",
    romaji: word.romaji || "",
    line_text: word.line_text || word.cue || "",
    start_ms: Number(word.start_ms || 0),
    end_ms: Number(word.end_ms || 0)
  }));
  const { ok, data } = await fetchJson("/api/learn/cards/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cards })
  }).catch(() => ({ ok: false, data: null }));
  if (ok && data && data.deck) applyDeck(data.deck);
}

function applyDeck(payload) {
  view.summary = payload || null;
  view.cards = (payload && payload.cards) || [];
  paintDeck();
}

async function loadDeck() {
  const gen = ++view.gen;
  view.loading = true;
  const { ok, data } = await fetchJson(
    `/api/learn/deck?deck=${encodeURIComponent(view.deck)}${scopeQuery(view.deck, view.songId)}`,
    { cache: "no-store" }
  ).catch(() => ({ ok: false, data: null }));
  view.loading = false;
  if (gen !== view.gen) return null;
  if (!ok || !data) {
    showToast(t("learn.loadFail"));
    return null;
  }
  applyDeck(data);
  return data;
}

async function dropCard(cardId) {
  if (!cardId) return;
  const { ok } = await fetchJson(`/api/learn/cards/${encodeURIComponent(cardId)}`, {
    method: "DELETE"
  }).catch(() => ({ ok: false }));
  if (!ok) {
    showToast(t("learn.recite.removeFail"));
    return;
  }
  showToast(t("learn.recite.removed"));
  await loadDeck();
}

async function restoreCard(cardId) {
  if (!cardId) return;
  const { ok } = await fetchJson("/api/learn/words/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word_id: cardId })
  }).catch(() => ({ ok: false }));
  if (!ok) {
    showToast(t("learn.recite.restoreFail"));
    return;
  }
  showToast(t("learn.recite.restored"));
  await loadDeck();
}

/* ------------------------------------------------------------- card flow */

function currentCard() {
  return run.queue[run.pos] || null;
}

function paintProgress() {
  const bar = $("reciteBar");
  const count = $("reciteCount");
  const span = run.queue.length || 1;
  if (bar) bar.style.width = `${Math.round((run.pos / span) * 100)}%`;
  if (count) {
    count.textContent =
      run.pos < run.total
        ? t("learn.recite.count", { i: run.pos + 1, n: run.total })
        : t("learn.recite.redrill");
  }
}

function stemHtml(card) {
  const stem = escapeHtml(card.stem || "");
  if (card.kind !== "blank") return stem;
  return stem.replace(/_{2,}/, `<em class="recite-gap">____</em>`);
}

function paintCard() {
  const card = currentCard();
  const box = $("reciteQs");
  const shell = $("reciteCard");
  const detail = $("reciteDetail");
  if (!card || !box) return;
  run.locked = false;
  stopSnippet();
  if (shell) {
    shell.hidden = false;
    shell.classList.toggle("is-blank", card.kind === "blank");
    shell.classList.remove("recite-shake");
  }
  if (detail) detail.hidden = true;
  paintProgress();
  const prompt = $("recitePrompt");
  if (prompt) prompt.textContent = card.prompt || "";
  const src = $("reciteSrc");
  // The listening card must never print the word it is asking for.
  if (src) src.innerHTML = card.audio ? "🎧" : stemHtml(card);
  const roma = $("reciteRoma");
  if (roma) roma.textContent = card.audio ? "" : (card.detail && card.detail.romaji) || "";
  const replay = $("reciteReplay");
  if (replay) replay.hidden = !card.audio || !hasSnippet(card.detail);
  box.innerHTML = `<div class="learn-choices">${(card.choices || [])
    .map(
      (choice) =>
        `<button type="button" class="learn-choice" data-cid="${choice.id}">${escapeHtml(choice.text)}</button>`
    )
    .join("")}</div>`;
  box.querySelectorAll(".learn-choice").forEach((btn) => {
    btn.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      pick(Number(btn.getAttribute("data-cid")), /** @type {HTMLElement} */ (btn));
    });
  });
  if (card.audio) playSnippet(card.detail, replay);
}

function showDetail(card) {
  const shell = $("reciteCard");
  const detail = $("reciteDetail");
  if (shell) shell.hidden = true;
  if (!detail) return;
  detail.hidden = false;
  const info = card.detail || {};
  const word = $("reciteDetailWord");
  if (word) word.textContent = info.text || card.stem || "";
  const roma = $("reciteDetailRoma");
  if (roma) roma.textContent = info.romaji || "";
  const zh = $("reciteDetailZh");
  if (zh) zh.textContent = info.zh || "";
  const from = $("reciteDetailFrom");
  if (from) {
    from.textContent = info.song_title
      ? t("learn.recite.from", { song: info.song_title })
      : t("learn.recite.fromLyrics");
  }
  const line = $("reciteDetailLine");
  if (line) {
    const text = info.line_text || "";
    const target = info.text || "";
    line.innerHTML =
      text && target && text.includes(target)
        ? escapeHtml(text).split(escapeHtml(target)).join(`<em>${escapeHtml(target)}</em>`)
        : escapeHtml(text || target);
  }
  const play = $("reciteDetailPlay");
  if (play) {
    play.hidden = !hasSnippet(info);
    if (!play.hidden) playSnippet(info, play);
  }
}

function record(card, ok) {
  if (!run.verdict.has(card.card_id)) run.verdict.set(card.card_id, ok);
}

/** A missed card goes to the back of the round — 百词斩's "until you get it". */
function requeue(card) {
  const tries = (run.tries.get(card.card_id) || 0) + 1;
  run.tries.set(card.card_id, tries);
  if (tries > MAX_REDRILL) return;
  const pending = run.queue.slice(run.pos + 1).some((item) => item.card_id === card.card_id);
  if (!pending) run.queue.push(card);
}

function advance() {
  stopSnippet();
  if (!run.active) return;
  run.pos += 1;
  if (run.pos >= run.queue.length) {
    const bar = $("reciteBar");
    if (bar) bar.style.width = "100%";
    finishRound();
    return;
  }
  paintCard();
}

function pick(cid, btn) {
  const card = currentCard();
  if (!card || run.locked) return;
  run.locked = true;
  const cardId = card.card_id;
  const roundGen = run.gen;
  const ok = cid === card.answer;
  const box = $("reciteQs");
  if (box) {
    box.querySelectorAll(".learn-choice").forEach((node) => {
      const id = Number(node.getAttribute("data-cid"));
      /** @type {HTMLButtonElement} */ (node).disabled = true;
      node.classList.toggle("is-ok", id === card.answer);
      node.classList.toggle("is-no", node === btn && !ok);
    });
  }
  record(card, ok);
  if (ok) {
    celebrateCorrect(btn || $("reciteSrc"), { line: true });
    window.setTimeout(() => {
      // Ignore a stale timer if the run was restarted or the card changed.
      if (run.active && run.gen === roundGen && currentCard()?.card_id === cardId) advance();
    }, 520);
    return;
  }
  playMissSfx();
  requeue(card);
  const shell = $("reciteCard");
  if (shell) {
    shell.classList.remove("recite-shake");
    void shell.offsetWidth;
    shell.classList.add("recite-shake");
  }
  window.setTimeout(() => {
    if (run.active && run.gen === roundGen && currentCard()?.card_id === cardId) showDetail(card);
  }, 420);
}

function admitUnknown() {
  const card = currentCard();
  if (!card || run.locked) return;
  run.locked = true;
  record(card, false);
  requeue(card);
  playMissSfx();
  showDetail(card);
}

async function finishRound() {
  const gen = run.gen;
  run.active = false;
  const answers = Array.from(run.verdict, ([card_id, ok]) => ({ card_id, ok }));
  const right = answers.filter((item) => item.ok).length;
  const pct = answers.length ? Math.round((right * 100) / answers.length) : 0;
  stopSnippet();
  hooks.showPane("learnReciteDone");
  hooks.setHead(deckTitle(run.deck), "");
  const num = $("reciteDoneNum");
  if (num) num.textContent = String(pct);
  const sub = $("reciteDoneSub");
  if (sub) sub.textContent = t("learn.recite.doneSub", { ok: right, n: answers.length });
  const note = $("reciteDoneDetail");
  if (note) note.textContent = t("common.saving");
  if (pct >= 60) celebrateCorrect(num, { line: true });
  const { ok, data } = await fetchJson("/api/learn/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deck: run.deck, song_id: run.songId || "", answers })
  }).catch(() => ({ ok: false, data: null }));
  if (gen !== run.gen) return;
  if (!ok || !data) {
    if (note) note.textContent = t("learn.recite.saveFail");
    return;
  }
  applyDeck(data.deck);
  if (note) {
    const streak = Number((data.deck && data.deck.streak) || 0);
    const left = Number((data.deck && data.deck.due) || 0);
    note.textContent = left
      ? t("learn.recite.doneLeft", { n: left })
      : t("learn.recite.doneStreak", { n: streak });
  }
}

async function startRound() {
  const gen = ++run.gen;
  const deck = view.deck;
  const songId = view.songId;
  const { ok, status, data } = await fetchJson(
    `/api/learn/session?deck=${encodeURIComponent(deck)}&size=${view.size || 10}${scopeQuery(
      deck,
      songId
    )}`,
    { cache: "no-store" }
  ).catch(() => ({ ok: false, status: 0, data: null }));
  if (gen !== run.gen) return;
  if (!ok || !data || !(data.cards || []).length) {
    // 409 是语义信号（今天没到期的），不是错误；重画一次让首页显示完成态。
    if (status === 409) {
      showToast(t("learn.recite.nothingDue"));
      await loadDeck();
      return;
    }
    showToast(t("learn.loadFail"));
    return;
  }
  run.deck = deck;
  run.songId = songId;
  run.queue = data.cards.slice();
  run.total = run.queue.length;
  run.pos = 0;
  run.verdict = new Map();
  run.tries = new Map();
  run.locked = false;
  run.active = true;
  hooks.showPane("learnReciteRun");
  hooks.setHead(deckTitle(deck), "");
  paintCard();
}

/* ----------------------------------------------------------------- entry */

export function stopRecite() {
  run.gen += 1;
  run.active = false;
  run.locked = false;
  run.queue = [];
  stopSnippet();
}

/** @param {"word" | "mistake"} [deck] @param {string} [songId] */
export async function openRecite(deck = "word", songId = "") {
  stopRecite();
  view.deck = deck === "mistake" ? "mistake" : "word";
  view.songId = view.deck === "word" ? String(songId || "") : "";
  view.songTitle = view.songId ? songTitle(state.playerSong) : "";
  view.summary = null;
  view.cards = [];
  hooks.showPane("learnRecite");
  paintHead();
  paintDeck();
  const data = await loadDeck();
  // 本地那份收藏是跨歌的，只在跨歌牌组里补导入，别在歌曲范围里混进别的歌。
  if (data && view.deck === "word" && !view.songId) await importLocalWords();
}

export function reciteSongId() {
  return view.songId;
}

/** Deck home is the natural "back" target from the run and result panes. */
export function reciteBack() {
  if (!$("learnReciteRun")?.hidden || !$("learnReciteDone")?.hidden) {
    stopRecite();
    openRecite(/** @type {"word" | "mistake"} */ (view.deck), view.songId);
    return true;
  }
  return false;
}

/** @param {{ showPane: (id: string) => void, setHead: (title: string, meta: string) => void }} deps */
export function bindRecite(deps) {
  hooks = Object.assign(hooks, deps || {});
  const start = $("reciteStart");
  if (start) start.onclick = () => startRound();
  const unknown = $("reciteUnknown");
  if (unknown) unknown.onclick = () => admitUnknown();
  const next = $("reciteDetailNext");
  if (next) next.onclick = () => advance();
  const replay = $("reciteReplay");
  if (replay)
    replay.onclick = () => {
      const card = currentCard();
      if (card) playSnippet(card.detail, replay);
    };
  const detailPlay = $("reciteDetailPlay");
  if (detailPlay)
    detailPlay.onclick = () => {
      const card = currentCard();
      if (card) playSnippet(card.detail, detailPlay);
    };
  const again = $("reciteDoneAgain");
  if (again) again.onclick = () => startRound();
  const back = $("reciteDoneBack");
  if (back)
    back.onclick = () => openRecite(/** @type {"word" | "mistake"} */ (view.deck), view.songId);
}
