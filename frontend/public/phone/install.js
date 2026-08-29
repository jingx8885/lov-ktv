import { installApi } from "./api.js";
import { ICO, paintTopRoom, paintTopWho } from "./ui/js/icons.js";
import { showToast } from "./ui/js/toast.js";
import { closeOverlay, openOverlay, showActionSheet } from "./ui/js/overlays.js";
import { loadWho } from "./ui/js/who.js";
import { showPage } from "./nav/js/pages.js";
import { showDeskPane, loadSongs } from "./desk/js/library.js";
import { loadRoom } from "./desk/js/queue.js";
import { runSearch } from "./search/js/hits.js";
import { stopPreview, togglePreview } from "./search/js/preview.js";
import { joinRoom, openTv, requestTvBind, needTvOrRoom, paintBindBtns } from "./room/js/join.js";
import { paintVocalMix, paintMix } from "./room/js/mix.js";
import { connectRoomRtc } from "./room/js/rtc.js";
import { ensurePhoneCtx, stopPhoneMic, paintPhoneMic } from "./player/js/mic.js";
import {
  exitEdit,
  enterEdit,
  ensureTimeline,
  updateAlignNow,
  renderAlignList,
  applyEditorTracks,
  syncEditAxis,
} from "./player/js/align.js";
import {
  setPlayIcon,
  refreshPlayIcon,
  unlockPlayerGesture,
  togglePlayer,
  playFromMs,
  pausePlayer,
  applyKaraokeGain,
  syncGuide,
  applyPlayerVocalMix,
  hookPlayerAudio,
  loadPlayerList,
  loadPlayerSong,
  openPlayer,
  bootPlayer,
  playNextSong,
  cueIndexAt,
} from "./player/js/playback.js";
import { setPlayerSheet } from "./player/js/sheet.js";
import { enterLearn, exitLearn } from "./player/js/learn.js";

installApi({
  ICO,
  paintTopRoom,
  paintTopWho,
  showToast,
  closeOverlay,
  openOverlay,
  showActionSheet,
  loadWho,
  showPage,
  showDeskPane,
  loadSongs,
  loadRoom,
  runSearch,
  stopPreview,
  togglePreview,
  joinRoom,
  openTv,
  requestTvBind,
  needTvOrRoom,
  paintBindBtns,
  paintVocalMix,
  paintMix,
  connectRoomRtc,
  ensurePhoneCtx,
  stopPhoneMic,
  paintPhoneMic,
  exitEdit,
  enterEdit,
  ensureTimeline,
  updateAlignNow,
  renderAlignList,
  applyEditorTracks,
  syncEditAxis,
  setPlayIcon,
  refreshPlayIcon,
  unlockPlayerGesture,
  togglePlayer,
  playFromMs,
  pausePlayer,
  applyKaraokeGain,
  syncGuide,
  applyPlayerVocalMix,
  hookPlayerAudio,
  loadPlayerList,
  loadPlayerSong,
  openPlayer,
  bootPlayer,
  playNextSong,
  cueIndexAt,
  setPlayerSheet,
  enterLearn,
  exitLearn,
});
