import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { lanOrigin, roomUrl } from "../../origin.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { state, LIB_LETTERS } from "../../state.js";
import { ICO } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { showActionSheet } from "../../ui/js/overlays.js";
import { handlePointError, syncWaitBar } from "../../ui/js/ads.js";

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
    if (!state.playerSong && api.bootPlayer) Promise.resolve(api.bootPlayer()).then(() => api.paintDeskLyrics());
  }
}

export function renderLibIndex(letters) {
  const have = new Map((letters || []).map((item) => [item.key, item.count]));
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

function songRow(song) {
  const canPlay = song.status === "ready";
  const canRetry = song.status === "failed";
  const canRecalculate = song.status === "ready";
  const canDelete = song.status !== "fetching" && song.status !== "separating";
  const pill = canPlay ? "" : `<em class="desk-pill">${STATUS[song.status] || song.status}</em>`;
  const mv = song.native_video ? `<em class="desk-pill mv">${t("phone.desk.officialMv")}</em>` : "";
  return `
        <div class="desk-row ${canPlay ? "" : "busy"}" data-song="${escapeHtml(song.id)}">
          <div class="desk-copy">
            <b>${escapeHtml(song.title)}</b>
            <span class="tiny">${escapeHtml(song.artist || t("common.unknownArtist"))} ${mv}${pill}</span>
            ${song.error ? `<span class="err">${escapeHtml(song.error)}</span>` : ""}
          </div>
          <div class="desk-actions">
            ${canPlay ? `<button class="row-action" data-queue="${song.id}" aria-label="${t("phone.desk.add")}">${ICO.plus}</button>` : ""}
            ${canRecalculate ? `<button class="row-action ghost" data-realign="${song.id}" aria-label="${t("phone.desk.recalculate")}">${ICO.refresh}</button>` : ""}
            ${canRetry ? `<button class="row-action ghost" data-retry="${song.id}" aria-label="${t("phone.desk.retry")}">${ICO.listen}</button>` : ""}
            ${canDelete ? `<button class="row-action ghost" data-del="${song.id}" aria-label="${t("phone.desk.delete")}">${ICO.trash}</button>` : ""}
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

function bindSongActions() {
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
        btn.classList.add("on");
        api.loadRoom({ room: data });
      };
    });
  $("songs")
    .querySelectorAll("[data-realign]")
    .forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.onclick = async (event) => {
        event.stopPropagation();
        btn.disabled = true;
        try {
          const started = await fetchJson(`/api/songs/${btn.dataset.realign}/realign`, {
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
            const current = await fetchJson(`/api/songs/${btn.dataset.realign}`, { cache: "no-store" }).catch(
              () => null
            );
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
          btn.disabled = false;
        }
      };
    });
  $("songs")
    .querySelectorAll("[data-retry]")
    .forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.onclick = async (event) => {
        event.stopPropagation();
        btn.disabled = true;
        await fetch(`/api/songs/${btn.dataset.retry}/retry`, { method: "POST" });
        loadSongs(false);
      };
    });
  $("songs")
    .querySelectorAll("[data-del]")
    .forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.onclick = async (event) => {
        event.stopPropagation();
        const go = await showActionSheet({
          title: t("phone.desk.deleteTitle"),
          message: t("phone.desk.deleteMsg"),
          confirm: t("phone.desk.delete"),
          danger: true
        });
        if (!go) return;
        btn.disabled = true;
        await fetch(`/api/songs/${btn.dataset.del}`, { method: "DELETE" });
        loadSongs(false);
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
  syncWaitBar(state.libSongs);
  bindSongActions();
}

export function bindLibrary() {
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
