import "./install.js";
import { $, setDomRoot } from "../shared/ui/js/dom.js";
import { bootI18n, onLangChange, applyDom, t } from "../shared/i18n/js/i18n.js";
import { PAGES, state, pageTitle, searchEmpty } from "./state.js";
import { openOverlay } from "./ui/js/overlays.js";
import { bindWho, loadWho } from "./ui/js/who.js";
import { bootAds, syncWaitBar } from "./ui/js/ads.js";
import { bindOverlays } from "./ui/js/overlays.js";
import { bindNav, showPage } from "./nav/js/pages.js";
import { bindSearch, paintSearchHits } from "./search/js/hits.js";
import { bindLibrary, loadSongs } from "./desk/js/library.js";
import { bindDeskLyrics, paintDeskLyrics } from "./desk/lyrics.js";
import { loadRoom } from "./desk/js/queue.js";
import { bindJoin, paintBindBtns } from "./room/js/room/join.js";
import { bindMix, paintVocalMix, paintLyricMode, paintDisplayMode } from "./room/js/room/mix.js";
import { bindRoomRtc } from "./room/js/room/rtc.js";
import { bindPlayback } from "./player/js/playback/ui.js";
import { updatePlayOrderBtns } from "./player/js/playback/queue.js";
import { bindPlayerSheet, syncPlayerSheetMeta } from "./player/js/playback/sheet.js";
import { bindAlign, updateAlignNow } from "./player/js/playback/align.js";
import { bindPhoneMic, paintPhoneMic } from "./player/js/playback/mic.js";
import { bindLearn } from "./player/js/learn/index.js";
import { api, installApi } from "./api.js";
import { installPlatform } from "./platform.js";

const mounted = new WeakSet();

/**
 * Mount the phone application into an explicit DOM root.  `deps` is an
 * optional test/host seam; supplied API ports are merged into the installed
 * adapter while existing browser and Android entry points remain compatible.
 * @param {ParentNode} root
 * @param {PhoneMountDeps} [deps]
 */
export function mount(root, deps = {}) {
  if (!root || mounted.has(root)) return () => {};
  mounted.add(root);
  if (deps.api) installApi(/** @type {PhoneApi} */ ({ ...api, ...deps.api }));
  if (deps.platform) installPlatform(deps.platform);
  const restoreDom = setDomRoot(root);
  /** @param {string} id */
  const must = (id) => {
    const el = $(id, root);
    if (!el) throw new Error("missing #" + id);
    return el;
  };

  const params = new URLSearchParams(location.search);
  if (params.get("login")) {
    location.replace("/login.html?" + params.toString());
  }
  const roomFromUrl = (params.get("room") || "").toUpperCase();
  if (roomFromUrl) {
    try {
      localStorage.setItem("room", roomFromUrl);
    } catch (_) {}
  }
  must("room").value = (roomFromUrl || localStorage.getItem("room") || "").toUpperCase();

  bootI18n();
  const offLang = onLangChange(() => {
    applyDom();
    must("topTitle").textContent = pageTitle(state.currentPage);
    const by = state.libState.by;
    must("libQ").placeholder =
      by === "artist"
        ? t("phone.desk.libPhArtist")
        : by === "title"
          ? t("phone.desk.libPhTitle")
          : t("phone.desk.libPh");
    loadWho();
    loadRoom();
    paintDeskLyrics();
    loadSongs();
    if (!must("page-search").hidden) {
      if (state.searchHits.length) {
        paintSearchHits(must("q").value.trim(), !!must("hits").querySelector(".list-more"));
      } else {
        must("hits").innerHTML = searchEmpty();
      }
    }
    paintVocalMix(must("vocalMix").classList.contains("on") ? 1 : 0);
    paintLyricMode(state.lyricMode, state.nowLanguage);
    paintDisplayMode(document.querySelector("#playerDisplayMode")?.classList.contains("on") ? "mv" : "lyrics");
    paintDeskLyrics();
    paintPhoneMic();
    updatePlayOrderBtns();
    syncPlayerSheetMeta();
    must("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
    must("playerVocal").setAttribute(
      "aria-label",
      state.playerVocal ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff")
    );
    if (state.playerSong) {
      must("playerTitle").textContent = state.playerSong.title;
      must("playerMeta").textContent =
        state.playerSong.artist && !String(state.playerSong.title).includes(state.playerSong.artist)
          ? state.playerSong.artist
          : "";
    }
    must("tlChain").textContent = state.chainRest ? t("phone.align.chainRest") : t("phone.align.chain");
    updateAlignNow();
    paintBindBtns();
  });

  bindWho();
  bootAds();
  bindOverlays();
  bindNav();
  bindSearch();
  bindLibrary();
  bindDeskLyrics();
  bindJoin();
  bindMix();
  paintLyricMode(state.lyricMode, state.nowLanguage);
  bindRoomRtc();
  bindPlayback();
  bindPlayerSheet();
  bindAlign();
  bindPhoneMic();
  bindLearn();

  const pollTimer = setInterval(() => {
    const scopedRoot = /** @type {any} */ (root);
    const desk = scopedRoot.getElementById ? scopedRoot.getElementById("page-desk") : $("page-desk", root);
    if (!desk || desk.hidden) return;
    loadRoom();
    if (state.libState.page <= 1) loadSongs(false);
    syncWaitBar(state.libSongs);
  }, 2000);

  const bootHash = (location.hash || "").replace("#", "");
  const bootPage = PAGES.includes(bootHash) ? bootHash : "desk";
  showPage(bootPage, null, false);
  if (bootHash === "room") openOverlay("roomSheet");

  const syncKeyboard = () => {
    const vv = window.visualViewport;
    const inset = vv ? Math.max(0, window.innerHeight - vv.height - vv.offsetTop) : 0;
    document.documentElement.style.setProperty("--kb", inset + "px");
  };
  if (window.visualViewport) {
    visualViewport.addEventListener("resize", syncKeyboard);
    visualViewport.addEventListener("scroll", syncKeyboard);
  }
  syncKeyboard();
  return () => {
    clearInterval(pollTimer);
    offLang();
    if (window.visualViewport) {
      visualViewport.removeEventListener("resize", syncKeyboard);
      visualViewport.removeEventListener("scroll", syncKeyboard);
    }
    restoreDom();
    mounted.delete(root);
  };
}

if (typeof document !== "undefined") mount(document.body || document);
