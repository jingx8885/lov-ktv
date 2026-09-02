import { installApi } from "./api.js";
import { roomCode, hostOrigin } from "./auth/js/login.js";
import { bindLiveMic, clearLiveMic, bindRoomRtc, micGainValue } from "./audio/js/mic.js";
import { startKeepAlive, schedulePlayRetries } from "./audio/js/keepalive.js";
import { hookAudio, unlockAudio, playEl, resumeCtxs, liveCtxs } from "./audio/js/unlock.js";
import { mediaUrl, prefetchQueue, applyMix, roomLine } from "./playback/js/media/mix.js";
import { silenceMtv, nativeMv, syncNativeMv, bindMtv } from "./playback/js/media/mtv.js";
import { paintSettings } from "./playback/js/remote/controls.js";
import { ensureStageFx, lyricsFingerprint, paint } from "./playback/js/lyric/paint.js";
import {
  pageVisible,
  canPlay,
  tick,
  applyRoom,
  watchRoom,
  startPlayback,
  stopPlayback,
  pauseAudio
} from "./playback/js/runtime/tick.js";

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
  applyRoom,
  watchRoom,
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
  roomLine,
  paintSettings,
  ensureStageFx,
  lyricsFingerprint,
  paint,
  hookAudio,
  unlockAudio,
  playEl,
  resumeCtxs,
  liveCtxs
});
