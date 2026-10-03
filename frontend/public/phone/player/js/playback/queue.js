import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { songArtist, songTitle } from "../../../../shared/ui/js/song.js";
import { songArt } from "../../../../shared/ui/js/art.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state, LIB_LETTERS } from "../../../state.js";
import { nextSongId } from "./state.js";
import { ICO, songLetter } from "../../../ui/js/icons.js";
import { setPlayerSheet, syncPlayerSheetMeta } from "./sheet.js";
import { api } from "../../../api.js";
import { showToast } from "../../../ui/js/toast.js";
import { togglePlayer, unlockPlayerGesture } from "./controls.js";
import { loadPlayerSong } from "./song.js";

// Whether the sheet shows the saved (favorites) set or the whole ready library,
// plus the substring filter typed into the sheet search box.
let playerListFavs = false;
let playerListQ = "";

export function playerListMode() {
  return playerListFavs ? "favs" : "all";
}

export function updatePlayOrderBtns() {
  const shuffle = state.playOrder === "shuffle";
  const icon = shuffle ? ICO.shuffle : ICO.seq;
  const label = shuffle ? t("common.shuffle") : t("common.seq");
  const main = $("playerOrder");
  if (main) {
    main.innerHTML = `${icon}<em id="playerOrderLabel">${label}</em>`;
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

function playerKey(song) {
  return (songTitle(song) + " " + songArtist(song)).toLowerCase();
}

function filteredCatalog() {
  const q = playerListQ.trim().toLowerCase();
  if (!q) return state.playerCatalog;
  return state.playerCatalog.filter((song) => playerKey(song).includes(q));
}

function playerRowHtml(song) {
  const cur = state.playerSong && state.playerSong.id;
  const fav = song.favorite !== false;
  return `
        <button
          type="button"
          class="list-row player-pick${song.id === cur ? " on" : ""}"
          data-pick="${escapeHtml(song.id)}"
          data-letter="${escapeHtml(song.letter || songLetter(song.title))}"
        >
          ${songArt(song, { playing: song.id === cur })}
          <span class="list-copy">
            <b>${escapeHtml(songTitle(song))}</b>
            <span class="tiny">${escapeHtml(songArtist(song) || t("common.unknownArtist"))}</span>
          </span>
          <span
            class="row-action ghost pick-fav${fav ? " on" : ""}"
            role="button"
            tabindex="-1"
            data-fav="${escapeHtml(song.id)}"
            aria-label="${fav ? t("phone.desk.unfavorite") : t("phone.desk.favorite")}"
            aria-pressed="${fav ? "true" : "false"}"
          >${ICO.star}</span>
        </button>`;
}

/** Keep the desk library star in sync when a song is toggled from the sheet. */
function syncDeskFavorite(songId, active) {
  const btn = document.querySelector(`#songs [data-favorite="${CSS.escape(String(songId))}"]`);
  if (!btn) return;
  btn.classList.toggle("on", active);
  btn.setAttribute("aria-pressed", String(active));
  btn.setAttribute("aria-label", active ? t("phone.desk.unfavorite") : t("phone.desk.favorite"));
}

async function togglePlayerFavorite(songId, favEl) {
  const song = state.playerCatalog.find((item) => item.id === songId);
  if (!song) return;
  const next = song.favorite === false;
  favEl.classList.add("is-busy");
  const result = await fetchJson(`/api/songs/${encodeURIComponent(songId)}/favorite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favorite: next })
  }).catch(() => null);
  favEl.classList.remove("is-busy");
  if (!result || !result.ok) {
    showToast((result && result.data && result.data.detail) || t("phone.desk.favoriteFailed"));
    return;
  }
  const active = !!result.data.favorite;
  song.favorite = active;
  syncDeskFavorite(songId, active);
  if (playerListFavs && !active) {
    // The sheet is the saved list: un-starring removes the row immediately.
    state.playerCatalog = state.playerCatalog.filter((item) => item.id !== songId);
    renderPlayerList();
    return;
  }
  favEl.classList.toggle("on", active);
  favEl.setAttribute("aria-pressed", String(active));
  favEl.setAttribute("aria-label", active ? t("phone.desk.unfavorite") : t("phone.desk.favorite"));
}

function paintIndexSpy() {
  const nav = $("playerIndex");
  const box = $("playerList");
  if (!nav || !box || nav.hidden) return;
  const boxTop = box.getBoundingClientRect().top;
  const heads = [...box.querySelectorAll("[data-sec]")];
  let letter = "";
  for (const head of heads) {
    // The last header still inside the sticky band wins.
    if (head.getBoundingClientRect().top - boxTop <= 34) letter = head.dataset.sec;
    else break;
  }
  nav.querySelectorAll("[data-player-letter]").forEach((btn) => {
    btn.classList.toggle("on", !!letter && btn.dataset.playerLetter === letter);
  });
}

let spyRaf = 0;
function queueIndexSpy() {
  if (spyRaf) return;
  spyRaf = requestAnimationFrame(() => {
    spyRaf = 0;
    paintIndexSpy();
  });
}

export function renderPlayerIndex() {
  const nav = $("playerIndex");
  const box = $("playerList");
  if (!nav) return;
  const rows = filteredCatalog();
  // The rail only earns its column once the list outgrows one screen, and
  // makes no sense while the search filter is trimming the rows.
  const show = rows.length >= 8 && !playerListQ.trim();
  nav.hidden = !show;
  if (!show) {
    nav.innerHTML = "";
    return;
  }
  const seen = new Set(rows.map((song) => song.letter || songLetter(song.title)));
  const letters = LIB_LETTERS.filter((key) => seen.has(key));
  nav.innerHTML = letters
    .map((key) => `<button type="button" class="lib-letter" data-player-letter="${key}">${key}</button>`)
    .join("");
  nav.querySelectorAll("[data-player-letter]").forEach((btn) => {
    btn.onclick = () => {
      const target =
        (box && box.querySelector(`[data-sec="${btn.dataset.playerLetter}"]`)) ||
        (box && box.querySelector(`[data-letter="${btn.dataset.playerLetter}"]`));
      if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
    };
  });
  paintIndexSpy();
}

function syncPlayerFilter() {
  const bar = $("playerFilter");
  const input = $("playerListQ");
  if (!bar || !input) return;
  const show = state.playerCatalog.length >= 12;
  bar.hidden = !show;
  if (!show && playerListQ) {
    playerListQ = "";
    input.value = "";
    const clear = $("playerListClear");
    if (clear) clear.hidden = true;
  }
}

export async function loadPlayerList() {
  const favs = await fetchJson("/api/songs?favorites=1", { cache: "no-store" }).catch(() => ({
    data: { songs: [] }
  }));
  let catalog = (favs.data.songs || []).filter((song) => song.status === "ready");
  playerListFavs = catalog.length > 0;
  // The player list is the saved set, but auto-advance must never hit an
  // empty queue just because nothing was favorited yet.  Fall back to the
  // whole ready library so finishing a track keeps the session going.
  if (!catalog.length) {
    const all = await fetchJson("/api/songs", { cache: "no-store" }).catch(() => ({ data: { songs: [] } }));
    catalog = ((all && all.data && all.data.songs) || []).filter((song) => song.status === "ready");
  }
  state.playerCatalog = catalog;
  renderPlayerList();
}

/**
 * Keep the currently playing row in sync without rebuilding the catalog.
 * Automatic next-track playback uses this path so updating the song cannot
 * scroll or re-render the catalog sheet while the singer is listening.
 * @param {string} songId
 */
export function markCurrentPlayerPick(songId) {
  const box = $("playerList");
  if (!box) return;
  const current = String(songId || "");
  box.querySelectorAll("[data-pick]").forEach((row) => {
    const on = row.dataset.pick === current;
    row.classList.toggle("on", on);
    const art = row.querySelector(".art");
    if (!art) return;
    const eq = art.querySelector(".art-eq");
    if (on && !eq) {
      art.insertAdjacentHTML("beforeend", '<span class="art-eq" aria-hidden="true"><i></i><i></i><i></i></span>');
    } else if (!on && eq) {
      eq.remove();
    }
  });
}

export function renderPlayerList() {
  const box = $("playerList");
  if (!box) return;
  syncPlayerFilter();
  const rows = filteredCatalog();
  const searching = !!playerListQ.trim();
  if (!rows.length) {
    box.innerHTML = searching
      ? `<div class="empty-state"><p>${t("phone.desk.noMatch")}</p></div>`
      : playerListFavs
        ? `<div class="empty-state"><p>${t("phone.player.emptyLib")}</p><button class="btn primary" type="button" data-go-search>${t("phone.desk.goSearch")}</button></div>`
        : `<div class="empty-state"><p>${t("phone.player.noPlayable")}</p></div>`;
  } else {
    let lastSec = "";
    box.innerHTML = rows
      .map((song) => {
        const letter = song.letter || songLetter(song.title);
        const head =
          letter !== lastSec
            ? `<div class="player-sec" data-sec="${escapeHtml(letter)}" aria-hidden="true">${escapeHtml(letter)}</div>`
            : "";
        lastSec = letter;
        return head + playerRowHtml(song);
      })
      .join("");
  }
  syncPlayerSheetMeta();
  renderPlayerIndex();
  const sheet = $("playerSheet");
  if (sheet && sheet.dataset.snap === "open") {
    const on = box.querySelector(".player-pick.on");
    if (on) on.scrollIntoView({ block: "nearest" });
    queueIndexSpy();
  }
}

export function bindPlayerList() {
  const box = $("playerList");
  const input = $("playerListQ");
  const clear = $("playerListClear");
  if (box) {
    box.addEventListener("scroll", queueIndexSpy, { passive: true });
    box.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      const fav = target.closest("[data-fav]");
      if (fav && box.contains(fav)) {
        event.stopPropagation();
        togglePlayerFavorite(fav.dataset.fav, fav);
        return;
      }
      const pick = target.closest("[data-pick]");
      if (!pick || !box.contains(pick)) return;
      unlockPlayerGesture();
      if (state.playerSong && pick.dataset.pick === state.playerSong.id) {
        // Tapping the playing row toggles playback instead of reloading it.
        togglePlayer();
        return;
      }
      setPlayerSheet("peek", true);
      loadPlayerSong(pick.dataset.pick, { play: true });
    });
  }
  if (input) {
    input.addEventListener("input", () => {
      playerListQ = input.value;
      if (clear) clear.hidden = !input.value;
      renderPlayerList();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && input.value) {
        input.value = "";
        input.dispatchEvent(new Event("input"));
      }
    });
  }
  if (clear) {
    clear.addEventListener("click", () => {
      if (!input) return;
      input.value = "";
      input.dispatchEvent(new Event("input"));
      input.focus();
    });
  }
}

let catalogRetry = false;

export function playNextSong() {
  const cur = state.playerSong && state.playerSong.id;
  const next = nextSongId(state.playerCatalog, cur, state.playOrder);
  if (!next) {
    // The track may have ended before the catalog finished loading (launch
    // straight into a song); retry once the list resolves instead of
    // silently stopping the listening session.
    if (!catalogRetry && api.loadPlayerList) {
      catalogRetry = true;
      Promise.resolve(api.loadPlayerList())
        .then(() => {
          catalogRetry = false;
          playNextSong();
        })
        .catch(() => {
          catalogRetry = false;
        });
    }
    return;
  }
  loadPlayerSong(next, { play: true, refreshPlayerCatalog: false });
}
