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
import { openPlaylistSheet } from "./playlists.js";

// Which catalog the sheet is drawing: a named playlist, the saved (favorites)
// set, or the whole ready library. The substring filter lives in playerListQ.
let playerListMode_ = "all";
let playerListQ = "";

export function playerListMode() {
  return playerListMode_;
}

export function activePlaylistId() {
  const source = String(state.playerSource || "");
  return source.startsWith("pl:") ? source.slice(3) : "";
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
  const inPlaylist = playerListMode_ === "pl";
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
          <span
            class="row-action ghost pick-pl"
            role="button"
            tabindex="-1"
            data-pladd="${escapeHtml(song.id)}"
            aria-label="${t("phone.pl.addTo")}"
          >${ICO.plAdd}</span>
          ${inPlaylist ? `<span
            class="row-action ghost pick-plremove"
            role="button"
            tabindex="-1"
            data-plremove="${escapeHtml(song.id)}"
            aria-label="${t("phone.pl.removeSong")}"
          >${ICO.trash}</span>` : ""}
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

/** Reflect the current song's star on the player dock chip. */
export function syncPlayerFavButton() {
  const btn = $("playerFav");
  if (!btn) return;
  const song = state.playerSong;
  const active = !!(song && song.favorite);
  btn.hidden = !song;
  btn.classList.toggle("on", active);
  btn.setAttribute("aria-pressed", String(active));
  btn.setAttribute("aria-label", active ? t("phone.desk.unfavorite") : t("phone.desk.favorite"));
}

async function postFavorite(songId, next) {
  const result = await fetchJson(`/api/songs/${encodeURIComponent(songId)}/favorite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favorite: next })
  }).catch(() => null);
  if (!result || !result.ok) {
    showToast((result && result.data && result.data.detail) || t("phone.desk.favoriteFailed"));
    return null;
  }
  return !!result.data.favorite;
}

/**
 * Persist one star change and repaint every place that mirrors it: the saved
 * catalog, the desk library row, the dock chip and the sheet row.
 */
export async function setSongFavorite(songId, next, favEl) {
  const song = (state.playerCatalog || []).find((item) => item.id === songId);
  const active = await postFavorite(songId, next);
  if (active === null) return false;
  if (song) song.favorite = active;
  if (state.playerSong && state.playerSong.id === songId) {
    state.playerSong.favorite = active;
  }
  syncDeskFavorite(songId, active);
  syncPlayerFavButton();
  if (playerListMode_ === "favs" && !active) {
    // The sheet is the saved list: un-starring removes the row immediately.
    state.playerCatalog = state.playerCatalog.filter((item) => item.id !== songId);
    renderPlayerList();
    return true;
  }
  if (favEl) {
    favEl.classList.toggle("on", active);
    favEl.setAttribute("aria-pressed", String(active));
    favEl.setAttribute("aria-label", active ? t("phone.desk.unfavorite") : t("phone.desk.favorite"));
  }
  return true;
}

async function togglePlayerFavorite(songId, favEl) {
  const song = (state.playerCatalog || []).find((item) => item.id === songId);
  if (!song) return;
  favEl.classList.add("is-busy");
  await setSongFavorite(songId, song.favorite === false, favEl);
  favEl.classList.remove("is-busy");
}

/** Star toggle for the song that is playing right now. */
export async function toggleCurrentFavorite() {
  const song = state.playerSong;
  if (!song || !song.id) return;
  const btn = $("playerFav");
  if (btn) btn.disabled = true;
  await setSongFavorite(song.id, !song.favorite);
  if (btn) btn.disabled = false;
}

async function removeFromActivePlaylist(songId) {
  const pid = activePlaylistId();
  if (!pid) return;
  const result = await fetchJson(
    `/api/playlists/${encodeURIComponent(pid)}/songs/${encodeURIComponent(songId)}`,
    { method: "DELETE" }
  ).catch(() => null);
  if (!result || !result.ok) {
    showToast((result && result.data && result.data.detail) || t("common.saveFailed"));
    return;
  }
  state.playerCatalog = state.playerCatalog.filter((item) => item.id !== songId);
  const entry = (state.playlists || []).find((item) => item.id === pid);
  if (entry) entry.count = Math.max(0, (entry.count || 0) - 1);
  renderPlayerSources();
  renderPlayerList();
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

/** Source chips above the list: library, saved songs, and every playlist. */
export function renderPlayerSources() {
  const bar = $("playerSources");
  if (!bar) return;
  const lists = Array.isArray(state.playlists) ? state.playlists : [];
  const source = String(state.playerSource || "");
  const chip = (key, label, on, extra) =>
    `<button type="button" class="src-chip${on ? " on" : ""}${extra || ""}" data-src="${key}">${label}</button>`;
  bar.innerHTML =
    chip("all", t("phone.desk.lib"), playerListMode_ === "all") +
    chip("favs", t("phone.pl.favs"), playerListMode_ === "favs") +
    lists
      .map((item) =>
        chip(
          "pl:" + item.id,
          `${escapeHtml(item.name)}<em>${item.count || 0}</em>`,
          source === "pl:" + item.id,
          " src-pl"
        )
      )
      .join("") +
    `<button type="button" class="src-chip src-add" data-src-add aria-label="${t(
      "phone.pl.manage"
    )}">${ICO.plus}<em>${lists.length ? "" : t("phone.pl.new")}</em></button>`;
  bar.querySelectorAll("[data-src]").forEach((btn) => {
    btn.onclick = () => selectPlayerSource(btn.dataset.src);
  });
  const add = bar.querySelector("[data-src-add]");
  if (add) add.onclick = () => openPlaylistSheet("");
}

/** Switch the listening catalog; "pl:<id>" selects one named playlist. */
export async function selectPlayerSource(source) {
  source = String(source || "");
  if (source.startsWith("pl:") && source === state.playerSource) {
    // Re-tap the active playlist: manage it instead of reloading the same list.
    openPlaylistSheet("");
    return;
  }
  state.playerSource = source;
  localStorage.setItem("playerSource", source);
  if (!source.startsWith("pl:")) state.playerSourceName = "";
  await loadPlayerList();
}

export async function loadPlayerList() {
  const source = String(state.playerSource || "");
  let catalog = [];
  playerListMode_ = "";
  if (source.startsWith("pl:")) {
    const pid = source.slice(3);
    const res = await fetchJson(
      `/api/playlists/${encodeURIComponent(pid)}/songs`,
      { cache: "no-store" }
    ).catch(() => null);
    if (res && res.ok && res.data && res.data.playlist) {
      playerListMode_ = "pl";
      state.playerSourceName = String(res.data.playlist.name || "");
      const entry = (state.playlists || []).find((item) => item.id === pid);
      if (entry) entry.count = Number(res.data.total || 0);
      catalog = (res.data.songs || []).filter((song) => song.status === "ready");
    } else {
      // The list vanished (deleted elsewhere); fall back to the saved set.
      state.playerSource = "";
      localStorage.removeItem("playerSource");
      state.playerSourceName = "";
    }
  }
  if (!playerListMode_ && source === "all") {
    playerListMode_ = "all";
    const all = await fetchJson("/api/songs", { cache: "no-store" }).catch(() => ({
      data: { songs: [] }
    }));
    catalog = ((all && all.data && all.data.songs) || []).filter((song) => song.status === "ready");
  }
  if (!playerListMode_) {
    const favs = await fetchJson("/api/songs?favorites=1", { cache: "no-store" }).catch(() => ({
      data: { songs: [] }
    }));
    catalog = (favs.data.songs || []).filter((song) => song.status === "ready");
    // Explicit "favs" keeps the empty saved view; the auto source falls back
    // to the whole ready library so finishing a track keeps the session going.
    if (catalog.length || source === "favs") {
      playerListMode_ = "favs";
    } else {
      playerListMode_ = "all";
      const all = await fetchJson("/api/songs", { cache: "no-store" }).catch(() => ({
        data: { songs: [] }
      }));
      catalog = ((all && all.data && all.data.songs) || []).filter((song) => song.status === "ready");
    }
  }
  state.playerCatalog = catalog;
  renderPlayerSources();
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
      : playerListMode_ === "favs"
        ? `<div class="empty-state"><p>${t("phone.player.emptyLib")}</p><button class="btn primary" type="button" data-go-search>${t("phone.desk.goSearch")}</button></div>`
        : playerListMode_ === "pl"
          ? `<div class="empty-state"><p>${t("phone.pl.empty")}</p></div>`
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
  syncPlayerFavButton();
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
      const plremove = target.closest("[data-plremove]");
      if (plremove && box.contains(plremove)) {
        event.stopPropagation();
        removeFromActivePlaylist(plremove.dataset.plremove);
        return;
      }
      const pladd = target.closest("[data-pladd]");
      if (pladd && box.contains(pladd)) {
        event.stopPropagation();
        openPlaylistSheet(pladd.dataset.pladd);
        return;
      }
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
