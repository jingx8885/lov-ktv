import "./install.js";
import { $must } from "../shared/ui/js/dom.js";
import { bootI18n, onLangChange, applyDom, t } from "../shared/i18n/js/i18n.js";
import { PAGES, state, pageTitle, searchEmpty } from "./state.js";
import { openOverlay } from "./ui/js/overlays.js";
import { bindWho, loadWho } from "./ui/js/who.js";
import { bindOverlays } from "./ui/js/overlays.js";
import { bindNav, showPage } from "./nav/js/pages.js";
import { bindSearch, paintSearchHits } from "./search/js/hits.js";
import { bindLibrary, loadSongs } from "./desk/js/library.js";
import { loadRoom } from "./desk/js/queue.js";
import { bindJoin } from "./room/js/join.js";
import { bindMix, paintVocalMix, paintLyricMode } from "./room/js/mix.js?v=mix3";
import { bindRoomRtc } from "./room/js/rtc.js";
import { bindPlayback, updatePlayOrderBtns } from "./player/js/playback.js";
import { bindPlayerSheet, syncPlayerSheetMeta } from "./player/js/sheet.js";
import { bindAlign, updateAlignNow } from "./player/js/align.js";
import { bindPhoneMic, paintPhoneMic } from "./player/js/mic.js";
import { bindLearn } from "./player/js/learn.js";

const params = new URLSearchParams(location.search);
if (params.get("login")) {
  location.replace("/login.html?" + params.toString());
}
$must("room").value = (params.get("room") || localStorage.getItem("room") || "").toUpperCase();

bootI18n();
onLangChange(() => {
  applyDom();
  $must("topTitle").textContent = pageTitle(state.currentPage);
  const by = state.libState.by;
  $must("libQ").placeholder = by === "artist" ? t("phone.desk.libPhArtist") : by === "title" ? t("phone.desk.libPhTitle") : t("phone.desk.libPh");
  loadWho();
  loadRoom();
  loadSongs();
  if (!$must("page-search").hidden) {
    if (state.searchHits.length) {
      paintSearchHits($must("q").value.trim(), !!$must("hits").querySelector(".list-more"));
    } else {
      $must("hits").innerHTML = searchEmpty();
    }
  }
  paintVocalMix($must("vocalMix").classList.contains("on") ? 1 : 0);
  paintLyricMode(state.lyricMode, state.nowLanguage);
  paintPhoneMic();
  updatePlayOrderBtns();
  syncPlayerSheetMeta();
  $must("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
  $must("playerVocal").setAttribute("aria-label", state.playerVocal ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff"));
  if (state.playerSong) {
    $must("playerTitle").textContent = state.playerSong.title;
    $must("playerMeta").textContent = state.playerSong.artist && !String(state.playerSong.title).includes(state.playerSong.artist) ? state.playerSong.artist : "";
  }
  $must("tlChain").textContent = state.chainRest ? t("phone.align.chainRest") : t("phone.align.chain");
  updateAlignNow();
});

bindWho();
bindOverlays();
bindNav();
bindSearch();
bindLibrary();
bindJoin();
bindMix();
paintLyricMode(state.lyricMode, state.nowLanguage);
bindRoomRtc();
bindPlayback();
bindPlayerSheet();
bindAlign();
bindPhoneMic();
bindLearn();

setInterval(() => {
  const desk = document.getElementById("page-desk");
  if (!desk || desk.hidden) return;
  loadRoom();
  loadSongs();
}, 2000);

const bootHash = (location.hash || "").replace("#", "");
const bootPage = PAGES.includes(bootHash) ? bootHash : "desk";
showPage(bootPage, null, false);
if (bootHash === "room" || !$must("room").value) openOverlay("roomSheet");

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
