import { installApi } from "./api.js";
import { roomCode, hostOrigin } from "./auth/js/login.js";
import { bindLiveMic, clearLiveMic, bindRoomRtc, micGainValue } from "./audio/js/mic.js?v=paint3";
import { startKeepAlive, schedulePlayRetries } from "./audio/js/keepalive.js?v=paint3";
import { hookAudio, unlockAudio, playEl, resumeCtxs, liveCtxs } from "./audio/js/unlock.js";
import { mediaUrl, prefetchQueue, applyMix, syncVocal, roomLine } from "./playback/js/mix.js?v=stall1";
import { silenceMtv, nativeMv, syncNativeMv, bindMtv } from "./playback/js/mtv.js?v=stall1";
import { ensureStageFx, lyricsFingerprint, paint } from "./playback/js/lyrics.js?v=paint3";
import { pageVisible, canPlay, tick, startPlayback, stopPlayback, pauseAudio } from "./playback/js/tick.js?v=paint3";

installApi({
  roomCode,
  hostOrigin,
  bindLiveMic,
  clearLiveMic,
  bindRoomRtc,
  micGainValue,
  pageVisible,
  canPlay,
  tick,
  startPlayback,
  stopPlayback,
  pauseAudio,
  startKeepAlive,
  schedulePlayRetries,
  silenceMtv,
  nativeMv,
  syncNativeMv,
  bindMtv,
  mediaUrl,
  prefetchQueue,
  applyMix,
  syncVocal,
  roomLine,
  ensureStageFx,
  lyricsFingerprint,
  paint,
  hookAudio,
  unlockAudio,
  playEl,
  resumeCtxs,
  liveCtxs,
});
