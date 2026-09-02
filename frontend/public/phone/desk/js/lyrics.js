import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { renderCue, clusterTokens, normLyricMode } from "../../../shared/lyrics/js/paint.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { api } from "../../api.js";
import { songArtist, songTitle } from "../../../shared/ui/js/song.js";

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
  const entry = {
    key,
    text,
    zh: String(word?.zh || "").trim(),
    romaji: String(word?.romaji || "").trim(),
    cue: String(cue?.text || "").trim(),
    song: String(state.playerSong?.title || "").trim(),
    song_id: state.playerSong?.id || "",
    // 背诵牌组的详情卡和听音题要靠这三个字段，本地这份也一起留着。
    start_ms: Number(word?.start_ms || 0),
    end_ms: Number(word?.end_ms || 0),
    line_text: String(cue?.text || "").trim(),
    created_at: Date.now()
  };
  words.unshift(entry);
  try {
    localStorage.setItem(WORDS_KEY, JSON.stringify(words.slice(0, 300)));
  } catch (_) {}
  // 服务端建卡失败不该拦住收藏——下次进背诵页的批量导入会把它补上。
  fetchJson("/api/learn/cards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      song_id: entry.song_id,
      song_title: entry.song,
      item_key: entry.key,
      text: entry.text,
      zh: entry.zh,
      romaji: entry.romaji,
      line_text: entry.line_text,
      start_ms: entry.start_ms,
      end_ms: entry.end_ms
    })
  }).catch(() => {});
  showToast(t("phone.lyrics.wordAdded", { word: text }));
  return true;
}

function emptyView(message, action = "") {
  return `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${escapeHtml(message)}</p>${action}</div>`;
}

export function paintDeskLyrics() {
  const pane = $("deskLyrics");
  if (!pane || pane.hidden) return;
  const list = $("deskLyricsList");
  const title = $("deskLyricsTitle");
  const song = state.playerSong;
  const cues = state.playerLyrics?.cues || [];
  if (title) {
    const artist = song ? songArtist(song) : "";
    title.textContent = song ? `${songTitle(song)}${artist ? ` · ${artist}` : ""}` : t("phone.lyrics.noSong");
  }
  if (!list) return;
  if (!cues.length) {
    list.innerHTML = emptyView(
      song ? t("phone.lyrics.empty") : t("phone.lyrics.noSongHint"),
      song ? "" : `<button class="btn primary" type="button" data-go-player>${t("phone.lyrics.goListen")}</button>`
    );
    return;
  }
  const mode = normLyricMode(state.lyricMode || "all");
  list.innerHTML = cues
    .map(
      (cue, cueIndex) =>
        `<article class="desk-lyric-line lyrics" data-cue-index="${cueIndex}">${renderCue(cue, 1e12, mode)}</article>`
    )
    .join("");
  list.querySelectorAll(".desk-lyric-line").forEach((line) => {
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

export function bindDeskLyrics() {
  const study = $("deskStudyBook");
  if (study) {
    study.onclick = async () => {
      if (!state.playerSong) return showToast(t("phone.player.needSong"));
      if (state.currentPage !== "player") api.showPage("player");
      await api.enterLearn();
      api.openStudyBook();
    };
  }
  document.querySelectorAll("[data-go-player]").forEach((btn) => {
    btn.onclick = () => {
      if (state.playerSong) api.showPage("player");
    };
  });
  const list = $("deskLyricsList");
  if (list) {
    list.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-go-player]");
      if (btn && state.playerSong) api.showPage("player");
    });
  }
}
