import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { roomCode } from "../../auth/js/login.js";
import { mediaUrl, prefetchQueue, applyMix, roomLine, syncVocal } from "./mix.js?v=stall1";
import { bindMtv, silenceMtv, nativeMv, syncNativeMv } from "./mtv.js?v=stall1";
import { lyricsFingerprint, ensureStageFx } from "./lyrics.js?v=stall1";

export function pageVisible() {
  return document.visibilityState === "visible";
}

export function canPlay() {
  return state.armed && pageVisible() && state.isLeader;
}

export function srcHasSong(el, songId) {
  const src = String((el && (el.getAttribute("src") || el.currentSrc || el.src)) || "");
  return !!(songId && src.includes(songId));
}

export function songReallyEnded(el) {
  if (!el) return false;
  const dur = el.duration;
  const t = el.currentTime || 0;
  if (!Number.isFinite(dur) || dur < 2) return false;
  return t >= dur - 1.5;
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

export function restoreResume(el) {
  const t = state.resumeAt || 0;
  if (!el || t <= 1 || (el.currentTime || 0) >= 1) return;
  try { el.currentTime = t; } catch (err) {}
}

function bindStallGuard(el) {
  if (!el || el.dataset.stallGuard === "1") return;
  el.dataset.stallGuard = "1";
  el.addEventListener("timeupdate", () => {
    if ((el.currentTime || 0) > 0.25) state.resumeAt = el.currentTime;
  });
  el.addEventListener("waiting", () => { state.mediaStall = Date.now(); });
  el.addEventListener("stalled", () => { state.mediaStall = Date.now(); });
  el.addEventListener("playing", () => { state.mediaStall = 0; });
  el.addEventListener("canplay", () => { state.mediaStall = 0; });
}

function recoverSameSrc(el) {
  const t = el.currentTime || state.resumeAt || 0;
  if (t > 0.5) state.resumeAt = t;
  if (!el.getAttribute("src")) return;
  if (Date.now() - state.lastRecoverAt < 4000) return;
  state.lastRecoverAt = Date.now();
  el.load();
  el.addEventListener("loadedmetadata", () => {
    restoreResume(el);
    api.playEl(el).catch(() => {});
  }, { once: true });
}

function bindKaraokeFallback(karaoke, vocal, songId) {
  karaoke.onerror = () => {
    const t = karaoke.currentTime || state.resumeAt || 0;
    if (t > 0.5) {
      state.resumeAt = t;
      return;
    }
    if (state.mediaFallback === songId) return;
    state.mediaFallback = songId;
    karaoke.src = mediaUrl(songId, "original.mp3");
    karaoke.onloadedmetadata = () => {
      restoreResume(karaoke);
      syncVocal(karaoke.currentTime || 0);
    };
  };
  vocal.onerror = () => {
    const t = vocal.currentTime || state.resumeAt || 0;
    if (t > 0.5 || String(vocal.getAttribute("src") || "").includes("guide.m4a")) return;
    vocal.src = mediaUrl(songId, "guide.m4a");
    vocal.onloadedmetadata = () => restoreResume(vocal);
  };
}

export function claimLeader() {
  if (state.isLeader) return;
  state.isLeader = true;
  if (state.audioBus) state.audioBus.postMessage({ type: "claim", tabId: state.tabId });
}

export function pauseAudio() {
  ["karaoke", "vocal", "mtv"].forEach((id) => $(id).pause());
}

export function stopAudioOnly() {
  ["karaoke", "vocal"].forEach((id) => {
    const el = $(id);
    el.pause();
    el.removeAttribute("src");
    el.load();
  });
  $("mtv").pause();
}

export function stopPlayback() {
  state.lyrics = { cues: [] };
  state.skeleton = null;
  state.lastItem = "";
  state.resumeAt = 0;
  state.emptyNow = 0;
  state.mediaStall = 0;
  state.mediaFallback = "";
  state.lastRecoverAt = 0;
  state.lyricPaint.prev = "";
  state.lyricPaint.cur = "";
  state.lyricPaint.next = "";
  ["karaoke", "vocal", "mtv"].forEach((id) => {
    const el = $(id);
    el.pause();
    el.removeAttribute("src");
    el.load();
  });
  $("mtv").hidden = true;
  state.boundMtvSong = "";
  document.body.classList.remove("has-mtv", "has-native-mv");
  state.lastFxCue = -1;
  state.hookLines = new Set();
  if (state.stageFx) state.stageFx.clear();
}

export async function tick() {
  const code = roomCode() || (state.room && state.room.code);
  if (!code) return;
  /** @type {{ ok: boolean, data: Room }} */
  const roomHit = await fetchJson("/api/rooms/" + code);
  if (!roomHit.ok || !roomHit.data || !roomHit.data.code) return;
  state.room = roomHit.data;
  localStorage.setItem("tvRoom", state.room.code);
  prefetchQueue(state.room);
  const now = state.room.now_playing;
  $("qinfo").textContent = roomLine(state.room);
  if (!now) {
    state.emptyNow += 1;
    if (state.emptyNow < 3) return;
    stopPlayback();
    $("gate").hidden = true;
    $("title").textContent = "";
    $("meta").textContent = "";
    $("prev").innerHTML = "";
    $("cur").textContent = "";
    $("next").innerHTML = "";
    return;
  }
  state.emptyNow = 0;
  $("title").textContent = now.title;
  $("meta").textContent = `${now.artist || ""} · ${STATUS[now.status] || now.status}`;
  if (now.status !== "ready") {
    $("prev").innerHTML = "";
    $("cur").textContent = "";
    $("next").textContent = "";
    return;
  }
  const itemKey = now.id || now.song_id;
  if (state.lastItem !== itemKey) {
    state.lastItem = itemKey;
    state.lyricPaint.prev = "";
    state.lyricPaint.cur = "";
    state.lyricPaint.next = "";
    const lyricsHit = await fetchJson(`/media/${now.song_id}/lyrics.json?v=ja-kanji&t=${Date.now()}`);
    state.lyrics = lyricsHit.ok ? lyricsHit.data : { cues: [] };
    const skeletonHit = await fetchJson(`/media/${now.song_id}/skeleton.json`).catch(() => ({ ok: false, data: null }));
    state.skeleton = skeletonHit.ok ? skeletonHit.data : null;
    state.lastLyricsAt = Date.now();
    state.lastFxCue = -1;
    state.lastMtvSeek = 0;
    state.lastVocalSync = 0;
    state.boundMtvSong = "";
    syncNativeMv();
    state.hookLines = nativeMv() ? new Set() : (window.LovStageFx ? LovStageFx.hookTexts(state.lyrics.cues) : new Set());
    if (!nativeMv()) ensureStageFx();
    bindMtv(now.song_id);
    startPlayback();
  } else {
    applyMix();
    if (!document.body.classList.contains("has-mtv") && !$("mtv").getAttribute("src")) {
      bindMtv(now.song_id);
    }
    if (Date.now() - state.lastLyricsAt > 8000) {
      state.lastLyricsAt = Date.now();
      const prev = lyricsFingerprint(state.lyrics);
      fetchJson(`/media/${now.song_id}/lyrics.json?v=ja-kanji&t=${state.lastLyricsAt}`)
        .then(({ ok, data }) => {
          if (!ok || !data || !data.cues || lyricsFingerprint(data) === prev) return;
          state.lyrics = data;
          syncNativeMv();
        })
        .catch(() => {});
    }
    const karaoke = $("karaoke");
    if (pageVisible() && state.isLeader && wantsResume(karaoke)) {
      startPlayback();
    }
  }
}

export function startPlayback() {
  if (!pageVisible()) {
    pauseAudio();
    $("gate").hidden = false;
    return;
  }
  state.armed = true;
  claimLeader();
  if (!state.isLeader) return;
  const songId = state.room && state.room.now_playing && state.room.now_playing.song_id;
  if (!songId) return;
  const karaoke = $("karaoke");
  const vocal = $("vocal");
  bindStallGuard(karaoke);
  if (srcHasSong(karaoke, songId)) {
    applyMix();
    silenceMtv($("mtv"));
    restoreResume(karaoke);
    if (karaoke.error) {
      recoverSameSrc(karaoke);
    } else if (karaoke.paused && !isMediaStalled(karaoke) && !songReallyEnded(karaoke)) {
      api.playEl(karaoke).then(() => { $("gate").hidden = true; }).catch(() => {
        if (state.audioUnlocked) api.schedulePlayRetries();
        else $("gate").hidden = false;
      });
    } else if (!karaoke.paused) {
      $("gate").hidden = true;
    }
    if (vocal.paused && !isMediaStalled(vocal)) api.playEl(vocal).catch(() => {});
    const mtv = $("mtv");
    if (mtv && mtv.paused && karaoke.currentTime > 0.05 && !isMediaStalled(mtv)) api.playEl(mtv).catch(() => {});
    return;
  }
  state.resumeAt = 0;
  state.mediaFallback = "";
  state.mediaStall = 0;
  karaoke.src = mediaUrl(songId, "karaoke.m4a");
  vocal.src = mediaUrl(songId, "original.mp3");
  bindKaraokeFallback(karaoke, vocal, songId);
  applyMix();
  silenceMtv($("mtv"));
  if (state.audioUnlocked) api.hookAudio();
  if (!nativeMv()) {
    const fx = ensureStageFx();
    if (fx && state.lastFxCue < 0) fx.spawn();
  }
  const ready = () => {
    syncVocal(karaoke.currentTime || 0);
  };
  karaoke.onloadedmetadata = ready;
  vocal.onloadedmetadata = ready;
  api.playEl(karaoke).then(() => { $("gate").hidden = true; }).catch(() => {
    if (state.audioUnlocked) api.schedulePlayRetries();
    else $("gate").hidden = false;
  });
  api.playEl(vocal).catch(() => {});
  api.playEl($("mtv")).catch(() => {});
}

