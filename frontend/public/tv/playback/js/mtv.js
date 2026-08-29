import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { mediaRevFor, mediaUrl } from "./mix.js";

function nativePlayer() {
  return window.LovKtvNative && typeof window.LovKtvNative.playMtv === "function";
}

function killHtmlMtv(mtv) {
  if (!mtv) return;
  mtv.muted = true;
  mtv.defaultMuted = true;
  mtv.volume = 0;
  mtv.hidden = true;
  mtv.pause();
  if (mtv.getAttribute("src") || mtv.src) {
    mtv.removeAttribute("src");
    try { mtv.load(); } catch (err) {}
  }
}

function glassStage(on) {
  const root = document.documentElement;
  const body = document.body;
  if (root) {
    root.style.background = on ? "transparent" : "";
    root.style.backgroundColor = on ? "transparent" : "";
  }
  if (body) {
    body.style.background = on ? "transparent" : "";
    body.style.backgroundColor = on ? "transparent" : "";
  }
}

export function silenceMtv(mtv) {
  if (!mtv) return;
  mtv.muted = true;
  mtv.defaultMuted = true;
  mtv.volume = 0;
  if (nativePlayer()) killHtmlMtv(mtv);
}

export function nativeMv() {
  return !!(
    (state.skeleton && state.skeleton.has_video)
    || (state.lyrics && state.lyrics.native_video === true)
    || document.body.classList.contains("has-native-player")
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
  const htmlSrc = mediaUrl(songId, "mtv.mp4");
  const abs = (location.origin || "") + htmlSrc;
  if (nativePlayer()) {
    killHtmlMtv(mtv);
    document.body.classList.add("has-mtv", "has-native-player");
    glassStage(true);
    syncNativeMv();
    const bindKey = songId + ":" + (mediaRevFor(songId) || "");
    if (state.boundMtvSong === bindKey) return;
    state.boundMtvSong = bindKey;
    try { window.LovKtvNative.playMtv(abs); } catch (err) {}
    return;
  }
  const bindKey = songId + ":" + (mediaRevFor(songId) || "");
  if (state.boundMtvSong === bindKey && (mtv.getAttribute("src") || mtv.src)) return;
  state.boundMtvSong = bindKey;
  syncNativeMv();
  const cover = mediaUrl(songId, "cover.jpg");
  silenceMtv(mtv);
  mtv.onerror = () => {
    document.body.classList.add("has-mtv-cover");
    document.body.style.backgroundImage = "url(" + cover + ")";
    if (document.body.classList.contains("has-mtv")) return;
    mtv.hidden = true;
    document.body.classList.remove("has-mtv");
    state.boundMtvSong = "";
  };
  mtv.onloadeddata = () => {
    silenceMtv(mtv);
    mtv.hidden = false;
    document.body.classList.add("has-mtv");
    document.body.classList.remove("has-mtv-cover");
    document.body.style.backgroundImage = "";
    syncNativeMv();
    if (api.canPlay()) mtv.play().catch(() => {});
  };
  mtv.src = htmlSrc;
  silenceMtv(mtv);
}

