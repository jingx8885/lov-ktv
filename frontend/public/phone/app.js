import "./install.js";
import { $, setDomRoot } from "../shared/ui/js/dom.js";
import { bootI18n, onLangChange, applyDom, t } from "../shared/i18n/js/i18n.js";
import { PAGES, state, pageTitle, searchEmpty } from "./state.js";
import { openOverlay } from "./ui/js/overlays.js";
import { bindWho, loadWho } from "./ui/js/who.js";
import { bootAds } from "./ui/js/ads.js";
import { bindOverlays } from "./ui/js/overlays.js";
import { bindNav, showPage } from "./nav/js/pages.js";
import { bindSearch, paintSearchHits } from "./search/js/hits.js";
import { bindLibrary, loadSongs } from "./desk/js/library.js";
import { bindDeskLyrics, paintDeskLyrics } from "./desk/js/lyrics.js";
import { loadRoom } from "./desk/js/queue.js";
import { bindJoin, paintBindBtns } from "./room/js/room/join.js";
import { bindMix, paintVocalMix, paintLyricMode, paintDisplayMode } from "./room/js/room/mix.js";
import { bindRoomRtc } from "./room/js/room/rtc.js";
import { bindPlayback } from "./player/js/playback/ui.js";
import { updatePlayOrderBtns, bindPlayerList } from "./player/js/playback/queue.js";
import { bindPlayerSheet, syncPlayerSheetMeta } from "./player/js/playback/sheet.js";
import { bindPlaylists, refreshPlaylists, renderPlaylistSheet } from "./player/js/playback/playlists.js";
import { bindAlign, updateAlignNow } from "./player/js/playback/align.js";
import { bindPhoneMic, paintPhoneMic } from "./player/js/playback/mic.js";
import { bindLearn } from "./player/js/learn/index.js";
import { api, installApi } from "./api.js";
import { bootMediaCache } from "./media-cache.js";
import { installPlatform, phonePlatform } from "./platform.js";
import { noWifi } from "./origin.js";
import { songArtist, songTitle } from "../shared/ui/js/song.js";
import { songCoverUrl } from "../shared/ui/js/art.js";
import { cueIndexAt as cueIndexAtCues, cueLine } from "../shared/lyrics/js/paint.js";

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
  if (noWifi() && must("room").value) {
    // Cellular boot: drop the remembered TV room so nothing tries to join it.
    must("room").value = "";
    try {
      localStorage.removeItem("room");
    } catch (_) {}
  }

  bootMediaCache();
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
    paintDisplayMode();
    paintDeskLyrics();
    paintPhoneMic();
    updatePlayOrderBtns();
    syncPlayerSheetMeta();
    renderPlaylistSheet();
    if (api.renderPlayerSources) api.renderPlayerSources();
    must("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
    must("playerVocal").setAttribute(
      "aria-label",
      state.playerVocal ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff")
    );
    if (state.playerSong) {
      must("playerTitle").textContent = songTitle(state.playerSong);
      must("playerMeta").textContent = songArtist(state.playerSong);
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
  bindPlayerList();
  bindPlaylists();
  bindAlign();
  bindPhoneMic();
  bindLearn();
  refreshPlaylists();

  const pollTimer = setInterval(() => {
    const scopedRoot = /** @type {any} */ (root);
    const desk = scopedRoot.getElementById ? scopedRoot.getElementById("page-desk") : $("page-desk", root);
    if (!desk || desk.hidden) return;
    loadRoom();
    if (state.libState.page <= 1) loadSongs(false);
  }, 2000);

  // Keep the Android notification shade useful even when the WebView is
  // backgrounded.  A small heartbeat also picks up room changes and async
  // player loads without coupling every feature module to the native bridge.
  const syncNotification = () => {
    const page = state.currentPage === "player" ? "player" : "desk";
    const card = $("nowCard", root);
    let title = "";
    let artist = "";
    if (page === "player" && state.playerSong) {
      title = songTitle(state.playerSong);
      artist = songArtist(state.playerSong);
    } else if (page === "desk") {
      const hit = card && card.querySelector(".now-hit");
      const values = hit ? hit.querySelectorAll("b, .tiny") : [];
      title = values[0]?.textContent?.trim() || "";
      artist = values[1]?.textContent?.trim() || "";
    }
    const audio = $("playerAudio", root);
    const playing =
      page === "player"
        ? !!audio && !audio.paused && !!audio.currentSrc
        : !!$("nowBar", root) &&
          !$("nowBar", root).classList.contains("is-idle") &&
          !$("deskPause", root)?.classList.contains("on");
    // Cover art powers the lock-screen card; the song id is known on the
    // player page, and on the desk the rendered <img> carries the URL.
    let cover = "";
    if (page === "player") {
      const id = state.playerSong && (state.playerSong.id || state.playerSong.song_id);
      if (id) cover = songCoverUrl(id, state.playerSong.media_rev);
    } else {
      const img = card && card.querySelector(".now-hit img");
      if (img && img.getAttribute("src")) cover = img.getAttribute("src");
    }
    if (cover) cover = new URL(cover, location.href).href;
    const payload = { page, title, artist, playing, cover };
    if (page === "player" && audio && audio.currentSrc) {
      payload.position = audio.currentTime || 0;
      payload.duration = Number.isFinite(audio.duration) ? audio.duration : 0;
      // Current sung line for the shade/lock-screen second row.  The desk
      // page plays on the TV, so there is no local clock to sync lyrics to.
      const doc = /** @type {any} */ (state.playerLyrics || {});
      const cues = doc.cues || [];
      const off = Number(doc.offset_ms ?? doc.lyric_offset_ms);
      const t = Math.max(0, Math.round((audio.currentTime || 0) * 1000) + (Number.isFinite(off) ? off : 0));
      const idx = cueIndexAtCues(cues, t);
      const cue = idx >= 0 && t >= cues[idx].start_ms && t < cues[idx].end_ms ? cues[idx] : null;
      if (cue) {
        const trans = String(cue.translation || cue.zh || "").trim();
        const line = cueLine(cue).trim();
        payload.lyric = line && trans ? line + " / " + trans : line || trans;
        const next = cues[idx + 1];
        if (next) payload.lyricNext = cueLine(next).trim();
      }
    }
    if (phonePlatform.notification && typeof phonePlatform.notification.update === "function") {
      phonePlatform.notification.update(payload);
    }
  };
  const notificationTimer = setInterval(syncNotification, 1000);
  syncNotification();

  const bootHash = (location.hash || "").replace("#", "");
  const linkedSong = (params.get("song") || "").trim();
  const linkedLyrics = linkedSong && bootHash === "lyrics";
  const bootPage = PAGES.includes(bootHash) ? bootHash : noWifi() ? "player" : "desk";
  showPage(linkedLyrics ? "desk" : bootPage, linkedSong && !linkedLyrics ? linkedSong : null, false);
  if (linkedLyrics) {
    // Admin deep links can open the read-only lyric desk without requiring a
    // room. Loading the player data also keeps the lyric source identical to
    // what singers see on the listen page.
    Promise.resolve(api.loadPlayerSong(linkedSong, { play: false })).then(() => api.showDeskPane("lyrics"));
  }
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
    clearInterval(notificationTimer);
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
