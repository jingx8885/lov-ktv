import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { state, LIB_LETTERS } from "../../state.js";
import { ICO } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { openOverlay, showActionSheet } from "../../ui/js/overlays.js";

export function showDeskPane(name) {
  const pane = name === "lib" ? "lib" : "queue";
  $("queue").hidden = pane !== "queue";
  $("libPane").hidden = pane !== "lib";
  document.querySelectorAll("[data-desk]").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.desk === pane);
  });
  if (pane === "lib") loadSongs();
}

export function renderLibIndex(letters) {
  const have = new Map((letters || []).map((item) => [item.key, item.count]));
  $("libIndex").innerHTML = `<button type="button" class="lib-letter ${state.libState.letter ? "" : "on"}" data-lib-letter="">${t("phone.desk.letterAll")}</button>` +
    LIB_LETTERS.map((key) => {
      const n = have.get(key) || 0;
      const on = state.libState.letter === key ? "on" : "";
      return `<button type="button" class="lib-letter ${on}" data-lib-letter="${key}" ${n ? "" : "disabled"}>${key}</button>`;
    }).join("");
  $("libIndex").querySelectorAll("[data-lib-letter]").forEach((btn) => {
    btn.onclick = () => {
      state.libState.letter = btn.dataset.libLetter || "";
      state.libState.page = 1;
      loadSongs();
    };
  });
}

export function renderLibPager(data) {
  const pages = Math.max(1, data.pages || 1);
  const page = data.page || 1;
  const total = data.total || 0;
  if (!total) {
    $("libPager").innerHTML = "";
    return;
  }
  $("libPager").innerHTML = page < pages
    ? `<button type="button" class="list-more" data-lib-page="${page + 1}">${t("phone.desk.morePages", { page, pages })}</button>`
    : `<span class="lib-page-num">${t("phone.desk.nSongs", { n: total })}</span>`;
  $("libPager").querySelectorAll("[data-lib-page]").forEach((btn) => {
    btn.onclick = () => {
      state.libState.page = Number(btn.dataset.libPage);
      loadSongs();
      $("songs").scrollIntoView({ block: "start" });
    };
  });
}

export async function loadSongs() {
  const params = new URLSearchParams({
    q: state.libState.q,
    by: state.libState.by,
    letter: state.libState.letter,
    page: String(state.libState.page),
    count: "8",
  });
  /** @type {{ data: SongListPage }} */
  const loaded = await fetchJson("/api/songs?" + params.toString()).catch(() => null);
  if (!loaded) return;
  const data = loaded.data;
  const songs = data.songs || [];
  state.libState.page = data.page || state.libState.page;
  if ($("libCount")) $("libCount").textContent = (data.lib_total || data.total) ? String(data.lib_total || data.total) : "";
  const stamp = JSON.stringify({
    q: state.libState.q,
    by: state.libState.by,
    letter: state.libState.letter,
    page: data.page,
    pages: data.pages,
    total: data.total,
    letters: data.letters,
    rows: songs.map((song) => [song.id, song.status, song.error, song.title]),
  });
  if (stamp === state.libStamp && $("songs").children.length) return;
  state.libStamp = stamp;
  renderLibIndex(data.letters || []);
  renderLibPager(data);
  const emptyHint = state.libState.q || state.libState.letter
    ? `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.desk.noMatch")}</p><button class="btn" type="button" data-lib-clear>${t("phone.desk.clearFilter")}</button></div>`
    : `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.desk.emptyLib")}</p><button class="btn primary" type="button" data-go-search>${t("phone.desk.goSearch")}</button></div>`;
  $("songs").innerHTML = songs.map((song) => {
    const canPlay = song.status === "ready";
    const canRetry = song.status === "failed";
    const canDelete = song.status !== "fetching" && song.status !== "separating";
    const pill = canPlay ? "" : `<em class="desk-pill">${STATUS[song.status] || song.status}</em>`;
    const mv = song.native_video ? `<em class="desk-pill mv">${t("phone.desk.officialMv")}</em>` : "";
    return `
        <div class="desk-row ${canPlay ? "" : "busy"}">
          <div class="desk-copy">
            <b>${escapeHtml(song.title)}</b>
            <span class="tiny">${escapeHtml(song.artist || t("common.unknownArtist"))} ${mv}${pill}</span>
            ${song.error ? `<span class="err">${escapeHtml(song.error)}</span>` : ""}
          </div>
          <div class="desk-actions">
            ${canPlay ? `<button class="row-action" data-queue="${song.id}" aria-label="${t("phone.desk.add")}">${ICO.plus}</button>` : ""}
            ${canRetry ? `<button class="row-action ghost" data-retry="${song.id}" aria-label="${t("phone.desk.retry")}">${ICO.listen}</button>` : ""}
            ${canDelete ? `<button class="row-action ghost" data-del="${song.id}" aria-label="${t("phone.desk.delete")}">${ICO.trash}</button>` : ""}
          </div>
        </div>`;
  }).join("") || emptyHint;
  $("songs").querySelectorAll("[data-queue]").forEach((btn) => {
    btn.onclick = async (event) => {
      event.stopPropagation();
      const code = $("room").value.trim();
      if (!code) {
        openOverlay("roomSheet");
        return showToast(t("phone.desk.needRoom"));
      }
      btn.disabled = true;
      const { ok, data } = await fetchJson(`/api/rooms/${code}/queue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ song_id: btn.dataset.queue }),
      });
      btn.disabled = false;
      if (!ok) {
        showToast(data.detail || t("phone.desk.cantQueue"));
        loadSongs();
        return;
      }
      btn.classList.add("on");
      api.loadRoom();
    };
  });
  $("songs").querySelectorAll("[data-retry]").forEach((btn) => {
    btn.onclick = async (event) => {
      event.stopPropagation();
      btn.disabled = true;
      await fetch(`/api/songs/${btn.dataset.retry}/retry`, { method: "POST" });
      loadSongs();
    };
  });
  $("songs").querySelectorAll("[data-del]").forEach((btn) => {
    btn.onclick = async (event) => {
      event.stopPropagation();
      const go = await showActionSheet({ title: t("phone.desk.deleteTitle"), message: t("phone.desk.deleteMsg"), confirm: t("phone.desk.delete"), danger: true });
      if (!go) return;
      btn.disabled = true;
      await fetch(`/api/songs/${btn.dataset.del}`, { method: "DELETE" });
      loadSongs();
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
      loadSongs();
    };
  }
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
      loadSongs();
    }, 200);
  });
  $("libQ").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(state.libTimer);
      state.libState.q = $("libQ").value.trim();
      state.libState.page = 1;
      loadSongs();
    }
  });
  document.querySelectorAll("[data-lib-by]").forEach((btn) => {
    btn.onclick = () => {
      state.libState.by = btn.dataset.libBy || "all";
      state.libState.page = 1;
      document.querySelectorAll("[data-lib-by]").forEach((item) => {
        item.classList.toggle("on", item === btn);
      });
      $("libQ").placeholder = state.libState.by === "artist" ? t("phone.desk.libPhArtist") : state.libState.by === "title" ? t("phone.desk.libPhTitle") : t("phone.desk.libPh");
      loadSongs();
    };
  });
}

