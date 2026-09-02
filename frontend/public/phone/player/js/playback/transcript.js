import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { renderCue, clusterTokens, normLyricMode } from "../../../../shared/lyrics/js/paint.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { api } from "../../../api.js";

const WORDS_KEY = "lovktv.study.words";

export function getStudyWords() {
  try {
    const value = JSON.parse(localStorage.getItem(WORDS_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch (_) {
    return [];
  }
}

export function saveStudyWord(word, cue) {
  const text = String(word?.text || "").trim();
  if (!text) return false;
  const words = getStudyWords();
  const key = `${state.playerSong?.id || "song"}:${text}:${word?.start_ms || 0}`;
  if (words.some((item) => item.key === key)) {
    showToast(t("phone.lyrics.wordSaved"));
    return false;
  }
  words.unshift({
    key,
    text,
    zh: String(word?.zh || "").trim(),
    romaji: String(word?.romaji || "").trim(),
    cue: String(cue?.text || "").trim(),
    song: String(state.playerSong?.title || "").trim(),
    song_id: state.playerSong?.id || "",
    created_at: Date.now()
  });
  try {
    localStorage.setItem(WORDS_KEY, JSON.stringify(words.slice(0, 300)));
  } catch (_) {}
  showToast(t("phone.lyrics.wordAdded", { word: text }));
  return true;
}

function emptyView(message) {
  return `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${escapeHtml(message)}</p></div>`;
}

export function paintTranscript() {
  const pane = $("playerTranscript");
  if (!pane || pane.hidden) return;
  const list = $("transcriptList");
  const song = state.playerSong;
  const cues = state.playerLyrics?.cues || [];
  if (!list) return;
  if (!cues.length) {
    list.innerHTML = emptyView(song ? t("phone.lyrics.empty") : t("phone.lyrics.noSongHint"));
    return;
  }
  const mode = normLyricMode(state.lyricMode || "all");
  list.innerHTML = cues
    .map(
      (cue, cueIndex) =>
        `<article class="transcript-line lyrics" data-cue-index="${cueIndex}">${renderCue(cue, 1e12, mode)}</article>`
    )
    .join("");
  list.querySelectorAll(".transcript-line").forEach((line) => {
    const cue = cues[Number(line.dataset.cueIndex)];
    const tokens = clusterTokens(cue.tokens || []);
    line.querySelectorAll(".tok").forEach((node, index) => {
      const token = tokens[index];
      if (!token) return;
      node.classList.add("desk-lyric-word");
      node.setAttribute("role", "button");
      node.setAttribute("tabindex", "0");
      node.setAttribute("aria-label", `${token.text}${token.zh ? ` · ${token.zh}` : ""}`);
      const save = () => saveStudyWord(token, cue);
      node.addEventListener("click", save);
      node.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          save();
        }
      });
    });
  });
}

export function bindTranscript() {
  const study = $("transcriptStudyBook");
  if (study) {
    study.onclick = async () => {
      if (!state.playerSong) return showToast(t("phone.player.needSong"));
      if (state.currentPage !== "player") api.showPage("player");
      await api.enterLearn();
      api.openStudyBook();
    };
  }
}
