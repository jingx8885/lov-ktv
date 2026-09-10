import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { openRecite } from "./recite.js";

export const WORDS_PANES = ["learnWords"];

/** 词太少时四选一凑不满，提前提示比让用户撞上空题好。 */
const THIN_SONG = 4;

/** @type {{ showPane: (id: string) => void, setHead: (title: string, meta: string) => void }} */
let hooks = { showPane: () => {}, setHead: () => {} };

/**
 * `cut` 是「我已经会了」的词。默认为空——整首歌都要背，用户只砍掉认识的，
 * 而不是从零开始挑。
 * @type {{ songId: string, title: string, words: any[], cut: Set<string>, gen: number, saving: boolean }}
 */
const view = { songId: "", title: "", words: [], cut: new Set(), gen: 0, saving: false };

function paintHead() {
  hooks.setHead(t("learn.words.title"), view.title || "");
}

function keptCount() {
  return view.words.length - view.cut.size;
}

function paintCount() {
  const count = $("learnWordsCount");
  if (count) {
    count.textContent = t("learn.words.count", { n: keptCount(), cut: view.cut.size });
  }
  const restoreAll = $("learnWordsRestoreAll");
  if (restoreAll) restoreAll.hidden = !view.cut.size;
  const go = /** @type {HTMLButtonElement | null} */ ($("learnWordsGo"));
  if (!go) return;
  const empty = !keptCount();
  go.disabled = empty || view.saving;
  go.setAttribute("aria-busy", String(view.saving));
  go.classList.toggle("is-loading", view.saving);
  go.textContent = view.saving
    ? t("common.saving")
    : empty
      ? t("learn.words.confirmNone")
      : t("learn.words.confirm", { n: keptCount() });
}

/** 已掌握 / 学习中的角标；砍掉的词由行样式和撤销按钮表达，不再叠角标。 */
function badge(word) {
  if (word.mastered) return { cls: "is-mastered", text: t("learn.words.mastered") };
  if (word.known) return { cls: "is-known", text: t("learn.words.known") };
  return null;
}

/** 歌词行里把目标词挑出来，用户凭上下文判断认不认识。 */
function lineHtml(word) {
  const line = String(word.line_text || "");
  const target = String(word.text || "");
  if (!line) return "";
  const safe = escapeHtml(line);
  if (!target || !line.includes(target)) return safe;
  return safe.split(escapeHtml(target)).join(`<em>${escapeHtml(target)}</em>`);
}

function rowHtml(word) {
  const cut = view.cut.has(word.word_id);
  const mark = cut ? { cls: "is-skipped", text: t("learn.words.skipped") } : badge(word);
  const sub = [word.zh, word.romaji].filter(Boolean).join(" · ");
  const line = lineHtml(word);
  const label = t(cut ? "learn.words.undoAria" : "learn.words.cutAria", { word: word.text || "" });
  // word_id 是 sha1 十六进制，放进属性是安全的；词面只进文本节点。
  return `<div class="learn-word-row${cut ? " is-cut" : ""}" data-row="${escapeHtml(word.word_id)}">
      <span class="learn-word-copy">
        <b>${escapeHtml(word.text || "")}</b>
        ${sub ? `<span>${escapeHtml(sub)}</span>` : ""}
        ${line ? `<span class="learn-word-line">${line}</span>` : ""}
      </span>
      ${mark ? `<span class="learn-word-badge ${mark.cls}">${escapeHtml(mark.text)}</span>` : "<span></span>"}
      <button type="button" class="learn-word-cut${cut ? " is-undo" : ""}" data-cut="${escapeHtml(
        word.word_id
      )}" aria-label="${escapeHtml(label)}">${escapeHtml(t(cut ? "learn.words.undo" : "learn.words.cut"))}</button>
    </div>`;
}

function bindRows(scope) {
  scope.querySelectorAll("[data-cut]").forEach((btn) => {
    btn.addEventListener("click", () => toggleCut(btn.getAttribute("data-cut") || ""));
  });
}

function paintList() {
  const list = $("learnWordsList");
  if (!list) return;
  list.innerHTML = view.words.map(rowHtml).join("");
  bindRows(list);
}

/** 只重画动过的那一行：长歌几十行，整表重绘会把滚动位置甩回顶部。 */
function repaintRow(wordId) {
  const list = $("learnWordsList");
  const row = list && list.querySelector(`[data-row="${wordId}"]`);
  const word = view.words.find((item) => item.word_id === wordId);
  if (!row || !word) {
    paintList();
    return;
  }
  row.outerHTML = rowHtml(word);
  const fresh = list.querySelector(`[data-row="${wordId}"]`);
  if (fresh) bindRows(fresh);
}

function paintThin() {
  const thin = $("learnWordsThin");
  if (thin) thin.hidden = view.words.length >= THIN_SONG;
}

function paint() {
  paintHead();
  paintThin();
  paintList();
  paintCount();
}

function toggleCut(wordId) {
  if (!wordId || view.saving) return;
  if (view.cut.has(wordId)) view.cut.delete(wordId);
  else view.cut.add(wordId);
  repaintRow(wordId);
  paintCount();
}

function restoreAll() {
  if (view.saving || !view.cut.size) return;
  view.cut = new Set();
  paintList();
  paintCount();
}

async function save() {
  if (view.saving || !keptCount()) return;
  const gen = view.gen;
  const songId = view.songId;
  view.saving = true;
  paintCount();
  const keep = [];
  const skip = [];
  view.words.forEach((word) => {
    (view.cut.has(word.word_id) ? skip : keep).push(word.word_id);
  });
  const { ok } = await fetchJson(`/api/songs/${encodeURIComponent(songId)}/learn/words/setup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keep, skip })
  }).catch(() => ({ ok: false }));
  if (gen !== view.gen) return;
  view.saving = false;
  paintCount();
  if (!ok) {
    showToast(t("learn.words.saveFail"));
    return;
  }
  await openRecite("word", songId);
}

/**
 * 歌曲专属背词入口。首次进来先砍词；砍过一次之后直接进复习，不再拦一道。
 * @param {string} [songId]
 */
export async function openSongWords(songId = "") {
  const id = songId || (state.playerSong && state.playerSong.id) || "";
  if (!id) {
    showToast(t("learn.noSong"));
    return;
  }
  const gen = ++view.gen;
  view.songId = id;
  view.saving = false;
  const { ok, status, data } = await fetchJson(`/api/songs/${encodeURIComponent(id)}/learn/words`, {
    cache: "no-store"
  }).catch(() => ({ ok: false, status: 0, data: null }));
  if (gen !== view.gen) return;
  if (!ok || !data) {
    showToast(status === 409 ? t("learn.words.empty") : t("learn.words.loadFail"));
    return;
  }
  // 已经砍过词的歌不再重复问一遍，直接进这首歌的复习队列。
  if (!data.first_setup) {
    await openRecite("word", id);
    return;
  }
  view.title = String(data.title || "");
  view.words = Array.isArray(data.words) ? data.words : [];
  // 之前在别的歌里砍过的词保持砍掉——那个「我会了」的判断是全局的。
  view.cut = new Set(view.words.filter((word) => word.skipped).map((word) => word.word_id));
  hooks.showPane("learnWords");
  paint();
}

export function stopSongWords() {
  view.gen += 1;
  view.saving = false;
}

/** @param {{ showPane: (id: string) => void, setHead: (title: string, meta: string) => void }} deps */
export function bindSongWords(deps) {
  hooks = Object.assign(hooks, deps || {});
  const restore = $("learnWordsRestoreAll");
  if (restore) restore.onclick = () => restoreAll();
  const go = $("learnWordsGo");
  if (go) go.onclick = () => save();
}
