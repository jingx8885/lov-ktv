import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import { api } from "../../../api.js";
import { ICO } from "../../../ui/js/icons.js";
import { showToast } from "../../../ui/js/toast.js";
import { showActionSheet, closeOverlay, openOverlay } from "../../../ui/js/overlays.js";

// Picker context: which song the sheet is adding to a list (empty = manage).
let pickSongId = "";
// Rename context: the list currently being renamed through the bottom input.
let renameId = "";

function apiFail(data, fallback) {
  showToast((data && data.detail) || fallback || t("common.saveFailed"));
}

function paintSheetTitle() {
  const title = $("playlistSheetTitle");
  if (!title) return;
  title.textContent = pickSongId ? t("phone.pl.addTitle") : t("phone.pl.title");
}

function paintCreateRow() {
  const input = $("playlistName");
  const btn = $("playlistCreate");
  if (!input || !btn) return;
  if (renameId) {
    input.placeholder = t("phone.pl.renamePh");
    btn.textContent = t("common.save");
  } else {
    input.placeholder = t("phone.pl.namePh");
    btn.textContent = t("phone.pl.create");
  }
}

function rowHtml(item) {
  const count = t("phone.desk.nSongs", { n: item.count || 0 });
  if (pickSongId) {
    return `
      <button type="button" class="list-row pl-row" data-pl="${escapeHtml(item.id)}">
        <span class="pl-ico" aria-hidden="true">${ICO.note}</span>
        <span class="list-copy">
          <b>${escapeHtml(item.name)}</b>
          <span class="tiny">${count}</span>
        </span>
        <span class="row-action ghost pl-toggle${item.has_song ? " on" : ""}" aria-hidden="true">
          ${item.has_song ? ICO.check : ICO.plus}
        </span>
      </button>`;
  }
  return `
      <button type="button" class="list-row pl-row" data-pl="${escapeHtml(item.id)}">
        <span class="pl-ico" aria-hidden="true">${ICO.note}</span>
        <span class="list-copy">
          <b>${escapeHtml(item.name)}</b>
          <span class="tiny">${count}</span>
        </span>
        <span
          class="row-action ghost"
          role="button"
          tabindex="-1"
          data-plrename="${escapeHtml(item.id)}"
          aria-label="${t("phone.pl.rename")}"
        >${ICO.edit}</span>
        <span
          class="row-action ghost"
          role="button"
          tabindex="-1"
          data-pldelete="${escapeHtml(item.id)}"
          aria-label="${t("phone.pl.delete")}"
        >${ICO.trash}</span>
      </button>`;
}

function renderSheet() {
  const box = $("playlistList");
  if (!box) return;
  const lists = Array.isArray(state.playlists) ? state.playlists : [];
  paintSheetTitle();
  paintCreateRow();
  if (!lists.length) {
    box.innerHTML = `<div class="empty-state"><p>${t("phone.pl.none")}</p></div>`;
    return;
  }
  box.innerHTML = lists.map(rowHtml).join("");
}

function syncPlayerSheetTitle() {
  if (api.syncPlayerSheetMeta) api.syncPlayerSheetMeta();
}

/** Pull the owner's playlists and repaint the chips + the open sheet. */
export async function refreshPlaylists() {
  const result = await fetchJson("/api/playlists", { cache: "no-store" }).catch(() => null);
  if (result && result.ok && result.data) {
    state.playlists = Array.isArray(result.data.playlists) ? result.data.playlists : [];
  }
  if (api.renderPlayerSources) api.renderPlayerSources();
  const sheet = $("playlistSheet");
  if (sheet && !sheet.hidden) renderSheet();
}

/**
 * Open the playlist sheet. With a song id it is a picker (tap toggles that
 * song's membership); without one the sheet manages the lists themselves.
 * @param {string} songId
 */
export async function openPlaylistSheet(songId) {
  pickSongId = String(songId || "").trim();
  renameId = "";
  const input = $("playlistName");
  if (input) input.value = "";
  openOverlay("playlistSheet");
  renderSheet();
  const result = await fetchJson(
    "/api/playlists" + (pickSongId ? `?song_id=${encodeURIComponent(pickSongId)}` : ""),
    { cache: "no-store" }
  ).catch(() => null);
  if (result && result.ok && result.data) {
    state.playlists = Array.isArray(result.data.playlists) ? result.data.playlists : [];
    if (api.renderPlayerSources) api.renderPlayerSources();
  }
  renderSheet();
}

async function toggleMembership(playlist) {
  const inList = !!playlist.has_song;
  const url = `/api/playlists/${encodeURIComponent(playlist.id)}/songs`;
  const result = inList
    ? await fetchJson(url + "/" + encodeURIComponent(pickSongId), { method: "DELETE" }).catch(() => null)
    : await fetchJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ song_id: pickSongId })
      }).catch(() => null);
  if (!result || !result.ok) {
    apiFail(result && result.data);
    return;
  }
  playlist.has_song = !inList;
  playlist.count = Math.max(0, (playlist.count || 0) + (inList ? -1 : 1));
  showToast(inList ? t("phone.pl.removedFrom", { name: playlist.name }) : t("phone.pl.addedTo", { name: playlist.name }));
  if (api.renderPlayerSources) api.renderPlayerSources();
  renderSheet();
  // The player sheet may be showing this very playlist; keep rows in sync.
  if (state.playerSource === "pl:" + playlist.id && api.loadPlayerList) {
    await api.loadPlayerList();
  }
}

async function submitCreateRow() {
  const input = $("playlistName");
  const btn = $("playlistCreate");
  const name = String((input && input.value) || "").trim();
  if (!name) {
    showToast(t("phone.pl.nameNeeded"));
    if (input) input.focus();
    return;
  }
  if (btn) btn.disabled = true;
  if (renameId) {
    const result = await fetchJson(`/api/playlists/${encodeURIComponent(renameId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    }).catch(() => null);
    if (btn) btn.disabled = false;
    if (!result || !result.ok) {
      apiFail(result && result.data);
      return;
    }
    const item = (state.playlists || []).find((pl) => pl.id === renameId);
    if (item) item.name = name;
    if (state.playerSource === "pl:" + renameId) state.playerSourceName = name;
    renameId = "";
    if (input) input.value = "";
    showToast(t("common.saved"));
    await refreshPlaylists();
    syncPlayerSheetTitle();
    return;
  }
  const result = await fetchJson("/api/playlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  }).catch(() => null);
  if (btn) btn.disabled = false;
  if (!result || !result.ok) {
    apiFail(result && result.data);
    return;
  }
  const created = result.data && result.data.playlist;
  if (input) input.value = "";
  await refreshPlaylists();
  // Picker flow: a fresh list immediately takes the picked song.
  if (pickSongId && created && created.id) {
    const item = (state.playlists || []).find((pl) => pl.id === created.id) || created;
    item.has_song = false;
    item.count = item.count || 0;
    await toggleMembership(item);
  }
}

async function confirmDelete(item) {
  const go = await showActionSheet({
    title: t("phone.pl.deleteTitle", { name: item.name }),
    message: t("phone.pl.deleteMsg"),
    confirm: t("phone.pl.delete"),
    danger: true
  });
  if (!go) return;
  const result = await fetchJson(`/api/playlists/${encodeURIComponent(item.id)}`, {
    method: "DELETE"
  }).catch(() => null);
  if (!result || !result.ok) {
    apiFail(result && result.data);
    return;
  }
  state.playlists = (state.playlists || []).filter((pl) => pl.id !== item.id);
  if (renameId === item.id) {
    renameId = "";
    const input = $("playlistName");
    if (input) input.value = "";
    paintCreateRow();
  }
  if (state.playerSource === "pl:" + item.id) {
    // Deleting the list being listened to drops back to the saved set.
    if (api.selectPlayerSource) await api.selectPlayerSource("");
  }
  await refreshPlaylists();
}

export function bindPlaylists() {
  const box = $("playlistList");
  if (box) {
    box.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      const rename = target.closest("[data-plrename]");
      if (rename && box.contains(rename)) {
        event.stopPropagation();
        const item = (state.playlists || []).find((pl) => pl.id === rename.dataset.plrename);
        if (!item) return;
        renameId = item.id;
        const input = $("playlistName");
        if (input) {
          input.value = item.name;
          input.focus();
        }
        paintCreateRow();
        return;
      }
      const del = target.closest("[data-pldelete]");
      if (del && box.contains(del)) {
        event.stopPropagation();
        const item = (state.playlists || []).find((pl) => pl.id === del.dataset.pldelete);
        if (item) confirmDelete(item);
        return;
      }
      const row = target.closest("[data-pl]");
      if (!row || !box.contains(row)) return;
      const item = (state.playlists || []).find((pl) => pl.id === row.dataset.pl);
      if (!item) return;
      if (pickSongId) {
        toggleMembership(item);
      } else if (api.selectPlayerSource) {
        closeOverlay("playlistSheet");
        api.selectPlayerSource("pl:" + item.id);
      }
    });
  }
  const create = $("playlistCreate");
  if (create) create.onclick = () => submitCreateRow();
  const input = $("playlistName");
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitCreateRow();
      }
    });
  }
}
