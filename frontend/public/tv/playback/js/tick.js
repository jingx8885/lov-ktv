import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { roomCode } from "../../auth/js/login.js";
import { mediaUrl, prefetchQueue, applyMix, roomLine, syncVocal } from "./mix.js";
import { bindMtv, silenceMtv, nativeMv, syncNativeMv } from "./mtv.js";
import { lyricsFingerprint, ensureStageFx } from "./lyrics.js";

export function pageVisible() {
  return document.visibilityState === "visible";
}

export function canPlay() {
  return state.armed && pageVisible() && state.isLeader;
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
    stopPlayback();
    $("gate").hidden = true;
    $("title").textContent = "";
    $("meta").textContent = "";
    $("prev").innerHTML = "";
    $("cur").textContent = "";
    $("next").innerHTML = "";
    return;
  }
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
        })
        .catch(() => {});
    }
    const karaoke = $("karaoke");
    if (pageVisible() && state.isLeader && karaoke && (karaoke.paused || !karaoke.getAttribute("src"))) {
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
  const playingSrc = String(karaoke.getAttribute("src") || karaoke.src || "");
  const sameSong = playingSrc.includes(songId);
  if (sameSong) {
    applyMix();
    silenceMtv($("mtv"));
    if (karaoke.paused) {
      api.playEl(karaoke).then(() => { $("gate").hidden = true; }).catch(() => {
        if (state.audioUnlocked) api.schedulePlayRetries();
        else $("gate").hidden = false;
      });
    } else {
      $("gate").hidden = true;
    }
    if (vocal.paused) api.playEl(vocal).catch(() => {});
    const mtv = $("mtv");
    if (mtv && mtv.paused && karaoke.currentTime > 0.05) api.playEl(mtv).catch(() => {});
    return;
  }
  karaoke.src = mediaUrl(songId, "karaoke.m4a");
  karaoke.onerror = () => { karaoke.src = mediaUrl(songId, "original.mp3"); };
  vocal.src = mediaUrl(songId, "original.mp3");
  vocal.onerror = () => { vocal.src = mediaUrl(songId, "guide.m4a"); };
  applyMix();
  silenceMtv($("mtv"));
  if (state.audioUnlocked) api.hookAudio();
  const fx = ensureStageFx();
  if (fx && state.lastFxCue < 0) fx.spawn();
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

