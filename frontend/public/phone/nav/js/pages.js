import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state, PAGES, pageTitle } from "../../state.js";
import { openOverlay } from "../../ui/js/overlays.js";
import { paintTopRoom } from "../../ui/js/icons.js";

export function showPage(name, songId, push) {
  if (name === "upload") name = "search";
  if (name === "room") {
    openOverlay("roomSheet");
    name = PAGES.includes(state.currentPage) ? state.currentPage : "desk";
  }
  if (!PAGES.includes(name)) name = "desk";
  if (name !== "player") {
    api.exitLearn();
    api.exitEdit();
    api.pausePlayer();
    if (api.setPlayerSheet) api.setPlayerSheet("peek", false);
  }
  state.currentPage = name;
  document.body.dataset.page = name;
  PAGES.forEach((id) => {
    $("page-" + id).hidden = id !== name;
  });
  document.querySelectorAll("[data-nav]").forEach((b) => b.classList.toggle("on", b.dataset.nav === name));
  $("topTitle").textContent = pageTitle(name) || pageTitle("desk");
  paintTopRoom();
  if (push !== false) {
    const url = new URL(location.href);
    url.hash = name;
    history.pushState({ page: name }, "", url);
  }
  if (name === "desk") {
    api.loadSongs();
    api.loadRoom();
  }
  if (name === "player") {
    api.setPlayerSheet("peek", false);
    api.loadPlayerList();
    if (songId) api.loadPlayerSong(songId, { play: true });
    else api.bootPlayer();
  }
}

export function bindNav() {
  document.querySelectorAll("[data-nav]").forEach((btn) => {
    btn.onclick = () => {
      showPage(btn.dataset.nav);
    };
  });
  document.addEventListener("click", (event) => {
    const goLib = event.target.closest("[data-go-lib]");
    if (goLib) api.showDeskPane("lib");
    const goSearch = event.target.closest("[data-go-search]");
    if (goSearch) showPage("search");
  });
  window.addEventListener("popstate", () => {
    const hash = (location.hash || "").replace("#", "");
    if (hash === "room") {
      showPage("desk", null, false);
      openOverlay("roomSheet");
      return;
    }
    showPage(hash || "desk", null, false);
  });
}
