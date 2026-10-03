import { $ } from "../../../../shared/ui/js/dom.js";
import { state } from "../../../state.js";

/** Build a versioned URL for a song asset. */
export function mediaUrl(songId, name) {
  const song = state.playerSong;
  const rev = (song && (song.id === songId || song.song_id === songId) && song.media_rev) || state.songMediaRev || "";
  return `/media/${songId}/${name}` + (rev ? `?v=${encodeURIComponent(rev)}` : "");
}

export function mediaPath(src) {
  try {
    return new URL(src, location.href).pathname;
  } catch (err) {
    return String(src || "").split("?")[0];
  }
}

export function mediaAhead(el, at) {
  try {
    const ranges = el.buffered;
    const t = Number(at) || 0;
    for (let i = 0; i < ranges.length; i += 1) {
      if (t >= ranges.start(i) - 0.05 && t <= ranges.end(i)) return ranges.end(i) - t;
    }
  } catch (err) {}
  return 0;
}

export function setPlayerCover(song) {
  const art = $("playerArt");
  const cover = $("playerCover");
  if (!art || !cover) return;
  art.classList.remove("has-cover");
  cover.hidden = true;
  cover.removeAttribute("src");
  if (!song || !song.id) return;
  cover.onload = () => {
    cover.hidden = false;
    art.classList.add("has-cover");
  };
  cover.onerror = () => {
    cover.hidden = true;
    cover.removeAttribute("src");
    art.classList.remove("has-cover");
  };
  cover.src = mediaUrl(song.id, "cover.jpg");
}

/** Wait until an audio element can actually start the requested source. */
export function waitMedia(el, gen, wantSrc) {
  return new Promise((resolve) => {
    if (!el || !el.getAttribute("src")) {
      resolve(false);
      return;
    }
    const want = mediaPath(wantSrc || el.getAttribute("src"));
    const isNew = () => el.readyState >= 3 && mediaPath(el.currentSrc || el.src) === want;
    if (isNew()) {
      resolve(true);
      return;
    }
    const finish = (ok) => {
      el.removeEventListener("canplay", onOk);
      el.removeEventListener("loadedmetadata", onOk);
      el.removeEventListener("error", onErr);
      resolve(ok);
    };
    const onOk = () => finish(gen === state.playerLoad && isNew());
    const onErr = () => finish(false);
    el.addEventListener("canplay", onOk, { once: true });
    el.addEventListener("loadedmetadata", onOk);
    el.addEventListener("error", onErr, { once: true });
    if (isNew()) finish(true);
    else
      setTimeout(() => {
        if (isNew()) finish(true);
      }, 0);
  });
}

/**
 * Lazy-load the guide vocal track. guide.m4a is a second full-length file
 * (~6MB per song) that is only audible inside the alignment editor, so the
 * player must not prefetch it on every song load.
 */
export function ensureGuideLoaded() {
  const guide = $("playerGuide");
  const url = state.playerGuideUrl || "";
  if (!guide || !url || state.playerGuideFailed === url) return false;
  const cur = guide.getAttribute("src");
  if (cur && mediaPath(cur) === mediaPath(url)) return true;
  guide.src = url;
  guide.load();
  guide.onerror = () => {
    state.playerGuideFailed = url;
    guide.removeAttribute("src");
    guide.load();
  };
  return true;
}

/**
 * Lazy-load the MTV video. A video is by far the heaviest per-song asset,
 * so the src is only attached while MV display mode is on.
 */
export function ensureMtvLoaded() {
  const mtv = $("playerMtv");
  const url = state.playerMtvUrl || "";
  if (!mtv || !url || state.playerMtvFailed === url) return false;
  const cur = mtv.getAttribute("src");
  if (cur && mediaPath(cur) === mediaPath(url)) return true;
  state.playerMtvTok += 1;
  const tok = state.playerMtvTok;
  mtv.onerror = () => {
    if (tok !== state.playerMtvTok) return;
    state.playerMtvFailed = url;
    mtv.hidden = true;
    const art = $("playerArt");
    if (art) art.classList.remove("has-mtv");
    mtv.removeAttribute("src");
    mtv.load();
  };
  mtv.onloadeddata = () => {
    if (tok !== state.playerMtvTok) return;
    const show = document.body.classList.contains("display-mv");
    mtv.hidden = !show;
    const art = $("playerArt");
    if (art) art.classList.toggle("has-mtv", show);
    const fullscreen = $("playerFullscreen");
    if (fullscreen) fullscreen.hidden = !show;
  };
  mtv.src = url;
  mtv.load();
  return true;
}

/** Detach the MTV video so switching away stops any in-flight download. */
export function releasePlayerMtv() {
  const mtv = $("playerMtv");
  if (!mtv) return;
  state.playerMtvTok += 1;
  mtv.pause();
  mtv.hidden = true;
  mtv.onerror = null;
  mtv.onloadeddata = null;
  mtv.removeAttribute("src");
  mtv.load();
  const art = $("playerArt");
  if (art) art.classList.remove("has-mtv");
  const fullscreen = $("playerFullscreen");
  if (fullscreen) fullscreen.hidden = true;
}
