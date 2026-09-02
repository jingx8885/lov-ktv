import { $ } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { STATUS } from "../../../../shared/ui/js/status.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { roomCode } from "../../../auth/js/login.js";
import {
  mediaRevFor,
  mediaUrl,
  prefetchQueue,
  applyMix,
  roomLine,
  activeTrackName,
  ensureActiveTrack,
  elementSongId,
  markTrackFallback,
  clearTrackFallback,
  trackFallbackActive
} from "../media/mix.js";
import { bindMtv, silenceMtv, nativeMv, syncNativeMv } from "../media/mtv.js";
import { sanitizeLyrics } from "../../../../shared/lyrics/js/paint.js";
import { lyricsFingerprint, ensureStageFx } from "../lyric/paint.js";
import { mediaEndedAt, roomItemIdentity, shouldReloadRoomItem, shouldStopEmptyNow } from "./state.js";
import { closeRoomWs, fetchRoomSnapshot, roomWsLive, snapshotStamp, watchRoom } from "../room/state.js";
import { nativeMtvAvailable, pauseNativeMtv, stopNativeMtv } from "../../../platform.js";

export { closeRoomWs, roomWsLive, watchRoom };

let applyGeneration = 0;

export function pageVisible() {
  // Keep the browser visibility signal available for autoplay policy checks;
  // it must not be used to pause an already-running TV session.
  return document.visibilityState === "visible";
}

export function canPlay() {
  // Once the TV has been armed by a user gesture, audio should keep running
  // when the browser tab is backgrounded or another page is in front.
  return state.armed && state.isLeader;
}

export function srcHasSong(el, songId) {
  const src = String((el && (el.getAttribute("src") || el.currentSrc || el.src)) || "");
  if (!songId || !src.includes(songId)) return false;
  const rev = mediaRevFor(songId);
  if (!rev) return true;
  return src.includes(`v=${encodeURIComponent(rev)}`) || src.includes(`v=${rev}`);
}

export function songReallyEnded(el) {
  if (!el) return false;
  return mediaEndedAt(el.currentTime, el.duration);
}

export function isMediaStalled(el) {
  if (!el) return false;
  if (state.mediaStall && Date.now() - state.mediaStall < 12000) return true;
  return el.networkState === 2 && el.readyState < 3;
}

export function wantsResume(el) {
  if (!el) return false;
  if (!el.getAttribute("src") && !el.currentSrc) return true;
  if (el.error) return true;
  if (!el.paused) return false;
  if (songReallyEnded(el)) return false;
  if (isMediaStalled(el)) return false;
  return true;
}

/** Remember a stall/recover position against the song it belongs to. */
export function rememberResume(songId, at) {
  const t = Number(at) || 0;
  if (!songId || t <= 0.25) return;
  state.resumeSong = songId;
  state.resumeAt = t;
}

export function clearResume() {
  state.resumeSong = "";
  state.resumeAt = 0;
}

/** The saved position, but only when it belongs to the song being asked about. */
export function resumeFor(songId) {
  if (!songId || (state.resumeSong && state.resumeSong !== songId)) return 0;
  return state.resumeAt || 0;
}

/**
 * A saved position belongs to one song only. Applying it to a different song
 * started the next pick partway in instead of at the first second.
 */
export function restoreResume(el) {
  const t = state.resumeAt || 0;
  if (!el || t <= 1 || (el.currentTime || 0) >= 1) return;
  if (state.resumeSong && elementSongId(el) !== state.resumeSong) return;
  try {
    el.currentTime = t;
  } catch (err) {}
}

function bindStallGuard(el) {
  if (!el || el.dataset.stallGuard === "1") return;
  el.dataset.stallGuard = "1";
  el.addEventListener("timeupdate", () => {
    rememberResume(elementSongId(el), el.currentTime);
  });
  el.addEventListener("waiting", () => {
    state.mediaStall = Date.now();
  });
  el.addEventListener("stalled", () => {
    state.mediaStall = Date.now();
  });
  el.addEventListener("playing", () => {
    state.mediaStall = 0;
  });
}

function recoverSameSrc(el) {
  const songId = elementSongId(el);
  const t = el.currentTime || resumeFor(songId);
  if (t > 0.5) rememberResume(songId, t);
  if (!el.getAttribute("src")) return;
  if (Date.now() - state.lastRecoverAt < 4000) return;
  state.lastRecoverAt = Date.now();
  el.load();
  el.addEventListener(
    "loadedmetadata",
    () => {
      restoreResume(el);
      api.playEl(el).catch(() => {});
    },
    { once: true }
  );
}

/**
 * A track that cannot load degrades to the other one, and the song stays
 * pinned there until it is skipped or the toggle asks for a retry. The pin
 * is what stops the next room snapshot from swapping the source back and
 * leaving the song bouncing between original and backing.
 */
function bindKaraokeFallback(karaoke, songId) {
  karaoke.onerror = () => {
    // Only this song's own progress counts as "already playing"; a leftover
    // position from the previous pick must not suppress the degrade path.
    const t = karaoke.currentTime || resumeFor(songId);
    if (t > 0.5) {
      rememberResume(songId, t);
      return;
    }
    if (trackFallbackActive(songId)) return;
    const failed = karaoke.dataset.track || activeTrackName(songId);
    const fallback = failed === "original.mp3" ? "karaoke.m4a" : "original.mp3";
    markTrackFallback(songId, fallback);
    karaoke.dataset.track = fallback;
    karaoke.src = mediaUrl(songId, fallback);
    karaoke.onloadedmetadata = () => {
      restoreResume(karaoke);
    };
    applyMix();
    if (typeof api.paintSettings === "function") api.paintSettings();
  };
}

export function claimLeader() {
  if (state.isLeader) return;
  state.isLeader = true;
  if (state.audioBus) state.audioBus.postMessage({ type: "claim", tabId: state.tabId });
}

export function pauseAudio() {
  ["karaoke", "mtv"].forEach((id) => $(id).pause());
  pauseNativeMtv();
}

export function stopAudioOnly() {
  ["karaoke"].forEach((id) => {
    const el = $(id);
    el.pause();
    el.removeAttribute("src");
    delete el.dataset.track;
    el.load();
  });
  $("mtv").pause();
}

export function setWaiting(on) {
  document.body.classList.toggle("is-waiting", !!on);
}

export function stopPlayback() {
  state.lyrics = { cues: [] };
  state.skeleton = null;
  state.lastItem = "";
  clearResume();
  state.emptyNow = 0;
  state.mediaStall = 0;
  clearTrackFallback();
  state.lastRecoverAt = 0;
  state.lyricPaint.prev = "";
  state.lyricPaint.cur = "";
  state.lyricPaint.next = "";
  ["karaoke", "mtv"].forEach((id) => {
    const el = $(id);
    el.pause();
    el.removeAttribute("src");
    delete el.dataset.track;
    el.load();
  });
  $("mtv").hidden = true;
  state.boundMtvSong = "";
  document.body.classList.remove("has-mtv", "has-native-mv", "has-native-player");
  stopNativeMtv();
  state.lastFxCue = -1;
  state.hookLines = new Set();
  if (state.stageFx) state.stageFx.clear();
}

export async function tick() {
  const code = roomCode() || (state.room && state.room.code);
  if (!code) return;
  /** @type {{ ok: boolean, data: Room }} */
  const roomHit = await fetchRoomSnapshot(code);
  if (roomHit.ok && roomHit.data && roomHit.data.code) {
    await applyRoom(roomHit.data);
    return;
  }
  if (state.room && state.room.code) await applyRoom(state.room);
}

export async function applyRoom(room) {
  if (!room || !room.code) return;
  const stamp = snapshotStamp(room);
  if (stamp === state.lastRoomStamp) return;
  state.lastRoomStamp = stamp;
  const generation = ++applyGeneration;
  state.room = room;
  localStorage.setItem("tvRoom", state.room.code);
  prefetchQueue(state.room);
  const now = state.room.now_playing;
  $("qinfo").textContent = roomLine(state.room);
  if (shouldStopEmptyNow(now)) {
    state.emptyNow = 0;
    stopPlayback();
    setWaiting(true);
    $("gate").hidden = true;
    $("title").textContent = "";
    $("meta").textContent = "";
    $("prev").innerHTML = "";
    $("cur").textContent = "";
    $("next").innerHTML = "";
    return;
  }
  state.emptyNow = 0;
  setWaiting(now.status !== "ready");
  $("title").textContent = now.title;
  $("meta").textContent = `${now.artist || ""} · ${STATUS[now.status] || now.status}`;
  if (now.status !== "ready") {
    const { itemKey, mediaRev } = roomItemIdentity(now);
    if (shouldReloadRoomItem(state.lastItem, state.lastMediaRev, now)) {
      state.lastItem = itemKey;
      state.lastMediaRev = mediaRev;
      stopAudioOnly();
      stopNativeMtv();
      state.boundMtvSong = "";
    }
    $("prev").innerHTML = "";
    $("cur").textContent = "";
    $("next").textContent = "";
    return;
  }
  const { itemKey, mediaRev } = roomItemIdentity(now);
  if (shouldReloadRoomItem(state.lastItem, state.lastMediaRev, now)) {
    state.lastItem = itemKey;
    state.lastMediaRev = mediaRev;
    state.lyricPaint.prev = "";
    state.lyricPaint.cur = "";
    state.lyricPaint.next = "";
    // Start the new track immediately. Lyrics/video metadata are secondary
    // and should never add network latency to a room skip.
    state.lyrics = { cues: [] };
    state.skeleton = null;
    clearResume();
    clearTrackFallback();
    stopAudioOnly();
    stopNativeMtv();
    state.boundMtvSong = "";
    syncNativeMv();
    startPlayback();
    const lyricsPromise = fetchJson(mediaUrl(now.song_id, "lyrics.json")).catch(() => ({
      ok: false,
      data: { cues: [] }
    }));
    const skeletonPromise = fetchJson(mediaUrl(now.song_id, "skeleton.json")).catch(() => ({
      ok: false,
      data: null
    }));
    const [lyricsHit, skeletonHit] = await Promise.all([lyricsPromise, skeletonPromise]);
    if (generation !== applyGeneration) return;
    state.lyrics = lyricsHit.ok ? sanitizeLyrics(lyricsHit.data) : { cues: [] };
    state.skeleton = skeletonHit.ok ? skeletonHit.data : null;
    state.lastLyricsAt = Date.now();
    state.lastFxCue = -1;
    state.lastMtvSeek = 0;
    state.boundMtvSong = "";
    syncNativeMv();
    state.hookLines = nativeMv()
      ? new Set()
      : window.LovStageFxTextHooks
        ? LovStageFxTextHooks.hookTexts(state.lyrics.cues)
        : new Set();
    if (!nativeMv()) ensureStageFx();
    bindMtv(now.song_id);
  } else {
    applyMix();
    syncNativeMv();
    if (nativeMtvAvailable()) {
      bindMtv(now.song_id);
    } else if (!document.body.classList.contains("has-mtv") && !$("mtv").getAttribute("src")) {
      bindMtv(now.song_id);
    }
    if (Date.now() - state.lastLyricsAt > 8000) {
      state.lastLyricsAt = Date.now();
      const prev = lyricsFingerprint(state.lyrics);
      fetchJson(mediaUrl(now.song_id, "lyrics.json"))
        .then(({ ok, data }) => {
          if (!ok || !data || !data.cues) return;
          const next = sanitizeLyrics(data);
          if (lyricsFingerprint(next) === prev) return;
          state.lyrics = next;
          syncNativeMv();
        })
        .catch(() => {});
    }
    const karaoke = $("karaoke");
    if (state.room && state.room.paused) {
      pauseAudio();
    } else if (state.armed && state.isLeader && wantsResume(karaoke)) {
      startPlayback();
    }
  }
}

export function startPlayback() {
  // A background tab may not start audio before a user gesture, but it must
  // not interrupt a session that was already unlocked and playing.
  if (!state.armed && !pageVisible()) {
    pauseAudio();
    $("gate").hidden = false;
    return;
  }
  if (state.room && state.room.paused) {
    pauseAudio();
    return;
  }
  state.armed = true;
  claimLeader();
  if (!state.isLeader) return;
  const songId = state.room && state.room.now_playing && state.room.now_playing.song_id;
  if (!songId) return;
  const karaoke = $("karaoke");
  bindStallGuard(karaoke);
  bindKaraokeFallback(karaoke, songId);
  ensureActiveTrack(songId);
  if (srcHasSong(karaoke, songId)) {
    applyMix();
    silenceMtv($("mtv"));
    restoreResume(karaoke);
    if (karaoke.error) {
      recoverSameSrc(karaoke);
    } else if (karaoke.paused && !isMediaStalled(karaoke) && !songReallyEnded(karaoke)) {
      api
        .playEl(karaoke)
        .then(() => {
          $("gate").hidden = true;
        })
        .catch(() => {
          if (state.audioUnlocked) api.schedulePlayRetries();
          else $("gate").hidden = false;
        });
    } else if (!karaoke.paused) {
      $("gate").hidden = true;
    }
    const mtv = $("mtv");
    if (
      mtv &&
      mtv.paused &&
      !karaoke.paused &&
      !state.mediaStall &&
      karaoke.readyState >= 3 &&
      karaoke.currentTime > 0.05 &&
      !isMediaStalled(mtv)
    ) {
      api.playEl(mtv).catch(() => {});
    }
    return;
  }
  clearResume();
  state.mediaStall = 0;
  karaoke.preload = "auto";
  karaoke.src = mediaUrl(songId, activeTrackName(songId));
  karaoke.dataset.track = activeTrackName(songId);
  bindKaraokeFallback(karaoke, songId);
  applyMix();
  silenceMtv($("mtv"));
  if (state.audioUnlocked) api.hookAudio();
  if (!nativeMv()) {
    const fx = ensureStageFx();
    if (fx && state.lastFxCue < 0) fx.spawn();
  }
  api
    .playEl(karaoke)
    .then(() => {
      $("gate").hidden = true;
    })
    .catch(() => {
      if (state.audioUnlocked) api.schedulePlayRetries();
      else $("gate").hidden = false;
    });
}
