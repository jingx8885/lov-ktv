import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state, LIB_LETTERS } from "../../../state.js";
import { nextSongId } from "./state.js";
import { ICO, songLetter } from "../../../ui/js/icons.js";
import { setPlayerSheet, syncPlayerSheetMeta } from "./sheet.js";
import { unlockPlayerGesture } from "./controls.js";
import { loadPlayerSong } from "./song.js";

export function updatePlayOrderBtns() {
  const shuffle = state.playOrder === "shuffle";
  const icon = shuffle ? ICO.shuffle : ICO.seq;
  const label = shuffle ? t("common.shuffle") : t("common.seq");
  const main = $("playerOrder");
  if (main) {
    main.innerHTML = `${icon}<em class="vh" id="playerOrderLabel">${label}</em>`;
    main.setAttribute("aria-label", shuffle ? t("common.shufflePlay") : t("common.seqPlay"));
    main.classList.toggle("on", shuffle);
  }
  const edit = $("playerOrderEdit");
  if (edit) {
    edit.innerHTML = icon;
    edit.setAttribute("aria-label", shuffle ? t("common.shufflePlay") : t("common.seqPlay"));
    edit.classList.toggle("on", shuffle);
  }
}

export function togglePlayOrder() {
  state.playOrder = state.playOrder === "shuffle" ? "seq" : "shuffle";
  localStorage.setItem("playOrder", state.playOrder);
  updatePlayOrderBtns();
}

export function renderPlayerIndex() {
  const nav = $("playerIndex");
  if (!nav) return;
  const have = new Set(state.playerCatalog.map((song) => song.letter || songLetter(song.title)));
  nav.innerHTML = LIB_LETTERS.map((key) => {
    const on = have.has(key);
    return `<button type="button" class="lib-letter" data-player-letter="${key}" ${on ? "" : "disabled"}>${key}</button>`;
  }).join("");
  nav.querySelectorAll("[data-player-letter]").forEach((btn) => {
    btn.onclick = () => {
      const row = $("playerList")?.querySelector(`[data-letter="${btn.dataset.playerLetter}"]`);
      if (row) row.scrollIntoView({ block: "start" });
    };
  });
}

export async function loadPlayerList() {
  const { data } = await fetchJson("/api/songs").catch(() => ({ data: { songs: [] } }));
  state.playerCatalog = (data.songs || []).filter((song) => song.status === "ready");
  renderPlayerList();
}

export function renderPlayerList() {
  const box = $("playerList");
  if (!box) return;
  const cur = state.playerSong && state.playerSong.id;
  box.innerHTML =
    state.playerCatalog
      .map(
        (song) => `
        <button type="button" class="list-row player-pick${song.id === cur ? " on" : ""}" data-pick="${song.id}" data-letter="${escapeHtml(song.letter || songLetter(song.title))}">
          <span class="list-copy">
            <b>${escapeHtml(song.title)}</b>
            <span class="tiny">${escapeHtml(song.artist || "")}</span>
          </span>
        </button>
      `
      )
      .join("") || `<div class="empty-state"><p>${t("phone.player.emptyLib")}</p></div>`;
  box.querySelectorAll("[data-pick]").forEach((btn) => {
    btn.onclick = () => {
      unlockPlayerGesture();
      setPlayerSheet("peek", true);
      loadPlayerSong(btn.dataset.pick, { play: true });
    };
  });
  syncPlayerSheetMeta();
  renderPlayerIndex();
  const on = box.querySelector(".player-pick.on");
  if (on) on.scrollIntoView({ block: "nearest" });
}

export function playNextSong() {
  const cur = state.playerSong && state.playerSong.id;
  const next = nextSongId(state.playerCatalog, cur, state.playOrder);
  if (!next) return;
  loadPlayerSong(next, { play: true });
}
