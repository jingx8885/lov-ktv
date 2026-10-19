import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { lanOrigin, roomUrl } from "../../origin.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { state, LIB_LETTERS } from "../../state.js";
import { ICO } from "../../ui/js/icons.js";
import { songArtist, songTitle } from "../../../shared/ui/js/song.js";
import { songArt } from "../../../shared/ui/js/art.js";
import { showToast } from "../../ui/js/toast.js";
import { showActionSheet } from "../../ui/js/overlays.js";
import { handlePointError } from "../../ui/js/ads.js";

function nearBottom(el) {
  if (!el) return false;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 160;
}

export function showDeskPane(name) {
  const pane = name === "lib" || name === "lyrics" ? name : "queue";
  $("queue").hidden = pane !== "queue";
  $("libPane").hidden = pane !== "lib";
  const lyricsPane = $("deskLyrics");
  if (lyricsPane) lyricsPane.hidden = pane !== "lyrics";
  document.querySelectorAll("[data-desk]").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.desk === pane);
  });
  if (pane === "lib") loadSongs();
  if (pane === "lyrics") {
    api.paintDeskLyrics();
    // 还没载入过播放器时先引导一次，拿到当前歌再重画。
    if (!state.playerSong && api.bootPlayer) Promise.resolve(api.bootPlayer()).then(() => api.paintDeskLyrics());
  }
}

export function renderLibIndex(letters) {
  const have = new Map((letters || []).map((item) => [item.key, item.count]));
  const total = [...have.values()].reduce((sum, n) => sum + n, 0);
  // A letter rail only earns its column once the catalog outgrows one screen.
  $("libIndex").hidden = !state.libState.letter && total < 24;
  $("libIndex").innerHTML =
    `<button type="button" class="lib-letter ${state.libState.letter ? "" : "on"}" data-lib-letter="">${t("phone.desk.letterAll")}</button>` +
    LIB_LETTERS.map((key) => {
      const n = have.get(key) || 0;
      const on = state.libState.letter === key ? "on" : "";
      return `<button type="button" class="lib-letter ${on}" data-lib-letter="${key}" ${n ? "" : "disabled"}>${key}</button>`;
    }).join("");
  $("libIndex")
    .querySelectorAll("[data-lib-letter]")
    .forEach((btn) => {
      btn.onclick = () => {
        state.libState.letter = btn.dataset.libLetter || "";
        state.libState.page = 1;
        loadSongs(false);
      };
    });
}

let queuedIds = new Set();

/** Keep the 点歌 button lit only while that song is still in the room queue. */
export function paintQueuedSongs(room) {
  if (room) {
    queuedIds = new Set(
      (room.queue || []).map((item) => String((item && item.song_id) || "")).filter(Boolean)
    );
  }
  const root = $("songs");
  if (!root) return;
  root.querySelectorAll("[data-queue]").forEach((btn) => {
    btn.classList.toggle("on", queuedIds.has(String(btn.dataset.queue || "")));
  });
}

function songRow(song) {
  const canPlay = song.status === "ready";
  const queued = queuedIds.has(String(song.id || ""));
  const pill = canPlay ? "" : `<em class="desk-pill">${STATUS[song.status] || song.status}</em>`;
  const mv = song.native_video ? `<em class="desk-pill mv">${t("phone.desk.officialMv")}</em>` : "";
  return `
        <div class="desk-row ${canPlay ? "" : "busy"}" data-song="${escapeHtml(song.id)}">
          ${songArt(song)}
          <div class="desk-copy">
            <b>${escapeHtml(songTitle(song))}</b>
            <span class="tiny">${escapeHtml(songArtist(song) || t("common.unknownArtist"))} ${mv}${pill}</span>
            ${song.error ? `<span class="err">${escapeHtml(song.error)}</span>` : ""}
          </div>
          <div class="desk-actions">
            ${canPlay ? `<button class="row-action queue-action${queued ? " on" : ""}" data-queue="${song.id}" aria-label="${t("phone.desk.add")}">${ICO.plus}<span>${t("phone.desk.add")}</span></button>` : ""}
            <button class="row-action ghost favorite-action${song.favorite ? " on" : ""}" data-favorite="${song.id}" aria-label="${song.favorite ? t("phone.desk.unfavorite") : t("phone.desk.favorite")}" aria-pressed="${song.favorite ? "true" : "false"}">${ICO.star}</button>
            <button class="row-action ghost more-action" data-more="${song.id}" aria-label="${t("phone.desk.more")}">${ICO.more}</button>
          </div>
        </div>`;
}

function emptyLibHint() {
  return state.libState.q || state.libState.letter
    ? `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.desk.noMatch")}</p><button class="btn" type="button" data-lib-clear>${t("phone.desk.clearFilter")}</button></div>`
    : `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.desk.emptyLib")}</p><button class="btn primary" type="button" data-go-search>${t("phone.desk.goSearch")}</button></div>`;
}

function renderLibTail(page, pages, total) {
  if (!total) {
    $("libPager").innerHTML = "";
    return;
  }
  if (page < pages) {
    $("libPager").innerHTML =
      `<button type="button" class="lib-page-num ${state.libLoading ? "" : "is-more"}" data-lib-more ${
        state.libLoading ? "disabled" : ""
      }>${state.libLoading ? t("common.loading") : t("common.loadMore")}</button>`;
    const more = $("libPager").querySelector("[data-lib-more]");
    if (more && !state.libLoading) more.onclick = () => loadSongs(true);
  } else {
    $("libPager").innerHTML = `<span class="lib-page-num">${t("phone.desk.nSongs", { n: total })}</span>`;
  }
}

function libSongById(id) {
  return (state.libSongs || []).find((song) => libSongId(song) === String(id));
}

/** Actions that used to be inline buttons now live behind one "more" menu. */
function songMenuItems(song) {
  const ready = song.status === "ready";
  const items = [{ id: "pladd", label: t("phone.pl.addTo") }];
  if (ready) items.push({ id: "edit", label: t("phone.player.align") });
  if (ready && state.songAdmin && song.can_realign !== false) {
    items.push({ id: "realign", label: t("phone.desk.recalculate") });
  }
  if (song.status === "failed" || (ready && !!String(song.error || "").trim())) {
    items.push({ id: "retry", label: t("phone.desk.retry") });
  }
  if (song.status !== "fetching" && song.status !== "separating") {
    items.push({ id: "delete", label: t("phone.desk.delete"), danger: true });
  }
  return items;
}

async function openSongMenu(id, btn) {
  const song = libSongById(id);
  if (!song) return;
  const items = songMenuItems(song);
  if (!items.length) return;
  const pick = await showActionSheet({
    title: songTitle(song),
    message: songArtist(song),
    items
  });
  if (!pick) return;
  if (pick === "pladd") {
    if (api.openPlaylistSheet) api.openPlaylistSheet(String(song.id));
  } else if (pick === "edit") {
    if (api.editSong) api.editSong(String(song.id));
  } else if (pick === "realign") {
    await realignSong(song, btn);
  } else if (pick === "retry") {
    await retrySong(song, btn);
  } else if (pick === "delete") {
    await deleteSong(song, btn);
  }
}

async function realignSong(song, btn) {
  const id = encodeURIComponent(String(song.id));
  if (btn) btn.disabled = true;
  try {
    const started = await fetchJson(`/api/songs/${id}/realign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rebuild_mtv: false, force: true })
    });
    if (!started.ok) throw new Error(started.data?.detail || t("phone.desk.recalculateFailed"));
    showToast(t("phone.desk.recalculateStarted"));
    await loadSongs(false, true);
    for (let attempt = 0; attempt < 360; attempt += 1) {
      await new Promise((resolve) => {
        setTimeout(resolve, 1500);
      });
      const current = await fetchJson(`/api/songs/${id}`, { cache: "no-store" }).catch(() => null);
      const status = current?.data?.status;
      if (status === "failed") throw new Error(t("phone.desk.recalculateFailed"));
      if (status !== "ready") continue;
      await loadSongs(false, true);
      showToast(t("phone.desk.recalculateDone"));
      return;
    }
    throw new Error(t("phone.desk.recalculateFailed"));
  } catch (err) {
    showToast(err instanceof Error ? err.message : t("phone.desk.recalculateFailed"));
    await loadSongs(false, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function retrySong(song, btn) {
  if (btn) btn.disabled = true;
  const result = await fetchJson(`/api/songs/${encodeURIComponent(String(song.id))}/retry`, {
    method: "POST"
  }).catch(() => null);
  if (!result || !result.ok) {
    showToast(result?.data?.detail || t("common.saveFailed"));
    if (btn) btn.disabled = false;
    return;
  }
  showToast(t("phone.desk.retry"));
  await loadSongs(false, true);
}

async function deleteSong(song, btn) {
  const go = await showActionSheet({
    title: t("phone.desk.deleteTitle"),
    message: t("phone.desk.deleteMsg"),
    confirm: t("phone.desk.delete"),
    danger: true
  });
  if (!go) return;
  if (btn) btn.disabled = true;
  await fetch(`/api/songs/${encodeURIComponent(String(song.id))}`, { method: "DELETE" });
  loadSongs(false);
}

function bindSongActions() {
  $("songs")
    .querySelectorAll("[data-favorite]")
    .forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.onclick = async (event) => {
        event.stopPropagation();
        const next = btn.getAttribute("aria-pressed") !== "true";
        btn.disabled = true;
        const result = await fetchJson(`/api/songs/${encodeURIComponent(btn.dataset.favorite)}/favorite`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ favorite: next })
        }).catch(() => null);
        btn.disabled = false;
        if (!result || !result.ok) {
          showToast(result?.data?.detail || t("phone.desk.favoriteFailed"));
          return;
        }
        const active = !!result.data.favorite;
        btn.classList.toggle("on", active);
        btn.setAttribute("aria-pressed", String(active));
        btn.setAttribute("aria-label", active ? t("phone.desk.unfavorite") : t("phone.desk.favorite"));
        if (api.loadPlayerList) api.loadPlayerList();
      };
    });
  $("songs")
    .querySelectorAll("[data-queue]")
    .forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.onclick = async (event) => {
        event.stopPropagation();
        const code = $("room").value.trim();
        if (api.needTvOrRoom && api.needTvOrRoom()) return;
        btn.disabled = true;
        const { ok, status, data } = await fetchJson(roomUrl(`/api/rooms/${code}/queue`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ song_id: btn.dataset.queue })
        });
        btn.disabled = false;
        if (!ok) {
          if (status === 402) handlePointError(status, data.detail);
          else showToast(lanOrigin() ? t("phone.room.lanFail") : data.detail || t("phone.desk.cantQueue"));
          loadSongs(false);
          return;
        }
        paintQueuedSongs(data);
        api.loadRoom({ room: data });
      };
    });
  $("songs")
    .querySelectorAll("[data-more]")
    .forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.onclick = (event) => {
        event.stopPropagation();
        openSongMenu(btn.dataset.more, btn);
      };
    });
  const goSearch = $("songs").querySelector("[data-go-search]");
  if (goSearch) goSearch.onclick = () => api.showPage("search");
  const clear = $("songs").querySelector("[data-lib-clear]");
  if (clear) {
    clear.onclick = () => {
      state.libState.q = "";
      state.libState.letter = "";
      state.libState.page = 1;
      $("libQ").value = "";
      loadSongs(false);
    };
  }
}

function libSongId(song) {
  return String((song && song.id) || "").trim();
}

function knownLibIds() {
  const fromState = (state.libSongs || []).map(libSongId);
  const fromDom = [...document.querySelectorAll("#songs [data-song]")].map((el) => el.getAttribute("data-song") || "");
  return new Set([...fromState, ...fromDom].filter(Boolean));
}

function paintLibRefresh(busy) {
  const btn = $("libRefresh");
  if (!btn) return;
  btn.disabled = !!busy;
  btn.classList.toggle("is-busy", !!busy);
}

export async function loadSongs(append = false, force = false) {
  if (force) {
    append = false;
    state.libStamp = "";
    state.libState.page = 1;
    state.libLoading = false;
  }
  if (state.libLoading) return;
  const have = state.libSongs || [];
  if (append && (Number(state.libState.page) || 1) >= (state.libPages || 1)) return;
  if (append && !have.length) return;
  const nextPage = append ? (Number(state.libState.page) || 1) + 1 : 1;
  const after = append ? libSongId(have[have.length - 1]) : "";
  state.libLoading = true;
  if (append) renderLibTail(state.libState.page, state.libPages || 1, state.libTotal || have.length);
  if (!append) paintLibRefresh(true);
  const params = new URLSearchParams({
    q: state.libState.q,
    by: state.libState.by,
    letter: state.libState.letter,
    page: String(nextPage),
    count: "8"
  });
  if (after) params.set("after", after);
  /** @type {{ data: SongListPage } | null} */
  const loaded = await fetchJson("/api/songs?" + params.toString(), { cache: "no-store" }).catch(() => null);
  state.libLoading = false;
  if (!append) paintLibRefresh(false);
  if (!loaded) {
    if (append) renderLibTail(state.libState.page, state.libPages || 1, state.libTotal || have.length);
    return;
  }
  const data = loaded.data;
  const songs = data.songs || [];
  state.libPages = Math.max(1, data.pages || 1);
  state.libTotal = Number(data.total || 0);
  if ($("libCount"))
    $("libCount").textContent = data.lib_total || data.total ? String(data.lib_total || data.total) : "";
  const filterKey = JSON.stringify({
    q: state.libState.q,
    by: state.libState.by,
    letter: state.libState.letter
  });
  if (!append) {
    const stamp =
      filterKey +
      ":" +
      JSON.stringify({
        pages: data.pages,
        total: data.total,
        letters: data.letters,
        rows: songs.map((song) => [song.id, song.status, song.error, song.title])
      });
    if (stamp === state.libStamp && $("songs").querySelector(".desk-row")) {
      // 语言切换等场景无需重绘歌曲卡片，但尾部文案仍需同步当前语言。
      renderLibTail(state.libState.page, state.libPages, state.libTotal || data.total || 0);
      return;
    }
    state.libStamp = stamp;
    state.libState.page = Number(data.page) || 1;
    state.libSongs = songs;
    renderLibIndex(data.letters || []);
    $("songs").innerHTML = songs.map(songRow).join("") || emptyLibHint();
    $("songs").scrollTop = 0;
  } else {
    const seen = knownLibIds();
    const extra = songs.filter((song) => {
      const id = libSongId(song);
      return id && !seen.has(id) && id !== after;
    });
    state.libSongs = have.concat(extra);
    if (!extra.length) {
      state.libState.page = state.libPages;
    } else {
      state.libState.page = Number(data.page) || nextPage;
      $("songs").insertAdjacentHTML("beforeend", extra.map(songRow).join(""));
    }
  }
  renderLibTail(state.libState.page, state.libPages, data.total || 0);
  bindSongActions();
  paintQueuedSongs();
}

export function bindLibrary() {
  document.addEventListener("lovktv-auth-change", () => {
    state.libStamp = "";
    loadSongs(false, true);
    if (api.refreshPlaylists) api.refreshPlaylists();
    if (api.loadPlayerList) api.loadPlayerList();
  });
  document.querySelectorAll("[data-desk]").forEach((btn) => {
    btn.onclick = () => showDeskPane(btn.dataset.desk);
  });
  $("libQ").addEventListener("input", () => {
    clearTimeout(state.libTimer);
    state.libTimer = setTimeout(() => {
      state.libState.q = $("libQ").value.trim();
      state.libState.page = 1;
      loadSongs(false);
    }, 200);
  });
  $("libQ").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(state.libTimer);
      state.libState.q = $("libQ").value.trim();
      state.libState.page = 1;
      loadSongs(false);
    }
  });
  document.querySelectorAll("[data-lib-by]").forEach((btn) => {
    btn.onclick = () => {
      state.libState.by = btn.dataset.libBy || "all";
      document.querySelectorAll("[data-lib-by]").forEach((item) => {
        item.classList.toggle("on", item === btn);
      });
      $("libQ").placeholder =
        state.libState.by === "artist"
          ? t("phone.desk.libPhArtist")
          : state.libState.by === "title"
            ? t("phone.desk.libPhTitle")
            : t("phone.desk.libPh");
      state.libState.page = 1;
      loadSongs(false);
    };
  });
  if (!$("songs").dataset.libScroll) {
    $("songs").dataset.libScroll = "1";
    $("songs").addEventListener("scroll", () => {
      if (state.libLoading) return;
      if (nearBottom($("songs"))) loadSongs(true);
    });
  }
  const refresh = $("libRefresh");
  if (refresh && !refresh.dataset.bound) {
    refresh.dataset.bound = "1";
    refresh.onclick = () => loadSongs(false, true);
  }
}
