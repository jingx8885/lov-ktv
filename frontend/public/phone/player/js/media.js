import { $ } from "../../../shared/ui/js/dom.js";
import { state } from "../../state.js";

/** Build a versioned URL for a song asset. */
export function mediaUrl(songId, name) {
  const song = state.playerSong;
  const rev = (song && (song.id === songId || song.song_id === songId) && song.media_rev)
    || state.songMediaRev
    || "";
  return `/media/${songId}/${name}` + (rev ? `?v=${encodeURIComponent(rev)}` : "");
}

export function mediaPath(src) {
  try { return new URL(src, location.href).pathname; } catch (err) { return String(src || "").split("?")[0]; }
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

/** Wait until an audio element has metadata for the requested source. */
export function waitMedia(el, gen, wantSrc) {
  return new Promise((resolve) => {
    if (!el || !el.getAttribute("src")) {
      resolve(false);
      return;
    }
    const want = mediaPath(wantSrc || el.getAttribute("src"));
    const isNew = () => el.readyState >= 1 && mediaPath(el.currentSrc || el.src) === want;
    if (isNew()) {
      resolve(true);
      return;
    }
    const finish = (ok) => {
      el.removeEventListener("loadedmetadata", onOk);
      el.removeEventListener("error", onErr);
      resolve(ok);
    };
    const onOk = () => finish(gen === state.playerLoad && isNew());
    const onErr = () => finish(false);
    el.addEventListener("loadedmetadata", onOk);
    el.addEventListener("error", onErr, { once: true });
    if (isNew()) finish(true);
    else setTimeout(() => { if (isNew()) finish(true); }, 0);
  });
}
