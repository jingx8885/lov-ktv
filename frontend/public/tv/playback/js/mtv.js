import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { mediaUrl } from "./mix.js";

export function silenceMtv(mtv) {
  mtv.muted = true;
  mtv.defaultMuted = true;
  mtv.volume = 0;
}

export function nativeMv() {
  return !!(
    (state.skeleton && state.skeleton.has_video)
    || (state.lyrics && state.lyrics.native_video === true)
  );
}

export function syncNativeMv() {
  const on = nativeMv();
  document.body.classList.toggle("has-native-mv", on);
  const plate = $("lyricPlate");
  if (!plate) return;
  plate.classList.toggle("bare", on);
  ["background", "backgroundImage", "border", "borderRadius", "boxShadow", "backdropFilter", "webkitBackdropFilter", "padding"].forEach((key) => {
    plate.style[key] = "";
  });
  if (on) {
    plate.style.background = "transparent";
    plate.style.backgroundImage = "none";
    plate.style.border = "0";
    plate.style.borderRadius = "0";
    plate.style.boxShadow = "none";
    plate.style.backdropFilter = "none";
    plate.style.webkitBackdropFilter = "none";
    plate.style.padding = "0 12px 4px";
  }
  if (!on) api.ensureStageFx();
}

export function bindMtv(songId) {
  const mtv = $("mtv");
  if (!songId) return;
  if (state.boundMtvSong === songId && (mtv.getAttribute("src") || mtv.src)) return;
  state.boundMtvSong = songId;
  syncNativeMv();
  silenceMtv(mtv);
  mtv.onerror = () => {
    if (document.body.classList.contains("has-mtv")) return;
    mtv.hidden = true;
    document.body.classList.remove("has-mtv", "has-native-mv");
    state.boundMtvSong = "";
  };
  mtv.onloadeddata = () => {
    silenceMtv(mtv);
    mtv.hidden = false;
    document.body.classList.add("has-mtv");
    syncNativeMv();
    if (api.canPlay()) mtv.play().catch(() => {});
  };
  mtv.src = mediaUrl(songId, "mtv.mp4");
  silenceMtv(mtv);
}

api.silenceMtv = silenceMtv;
api.nativeMv = nativeMv;
api.syncNativeMv = syncNativeMv;
api.bindMtv = bindMtv;
