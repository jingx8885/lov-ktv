import { $ } from "../shared/ui/js/dom.js";
import { PAGES } from "./state.js";
import { openOverlay } from "./ui/js/overlays.js";
import { bindWho } from "./ui/js/who.js";
import { bindOverlays } from "./ui/js/overlays.js";
import { bindNav, showPage } from "./nav/js/pages.js";
import { bindSearch } from "./search/js/hits.js";
import { bindLibrary, loadSongs } from "./desk/js/library.js";
import { loadRoom } from "./desk/js/queue.js";
import { bindJoin } from "./room/js/join.js";
import { bindMix } from "./room/js/mix.js";
import { bindRoomRtc } from "./room/js/rtc.js";
import { bindPlayback } from "./player/js/playback.js";
import { bindAlign } from "./player/js/align.js";
import { bindPhoneMic } from "./player/js/mic.js";

const params = new URLSearchParams(location.search);
if (params.get("login")) {
  location.replace("/login.html?" + params.toString());
}
$("room").value = (params.get("room") || localStorage.getItem("room") || "").toUpperCase();

bindWho();
bindOverlays();
bindNav();
bindSearch();
bindLibrary();
bindJoin();
bindMix();
bindRoomRtc();
bindPlayback();
bindAlign();
bindPhoneMic();

setInterval(() => {
  if (!$("page-desk").hidden) {
    loadRoom();
    loadSongs();
  }
}, 2000);

const bootHash = (location.hash || "").replace("#", "");
const bootPage = PAGES.includes(bootHash) ? bootHash : "desk";
showPage(bootPage, null, false);
if (bootHash === "room" || !$("room").value) openOverlay("roomSheet");

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
