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
import { joinRoom, openTv, requestTvBind, needTvOrRoom, paintBindBtns } from "./room/js/room/join.js";
import { paintVocalMix, paintMix } from "./room/js/room/mix.js";
import { connectRoomRtc } from "./room/js/room/rtc.js";
import { ensurePhoneCtx, stopPhoneMic, paintPhoneMic } from "./player/js/playback/mic.js";
import {
  exitEdit,
  enterEdit,
  ensureTimeline,
  updateAlignNow,
  renderAlignList,
  applyEditorTracks,
  syncEditAxis
} from "./player/js/playback/align.js";
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
  hookPlayerAudio
} from "./player/js/playback/controls.js";
import { loadPlayerList, playNextSong } from "./player/js/playback/queue.js";
import { loadPlayerSong, openPlayer, bootPlayer } from "./player/js/playback/song.js";
import { cueIndexAt } from "./player/js/playback/lyrics.js";
import { setPlayerSheet } from "./player/js/playback/sheet.js";
import { enterLearn, exitLearn, openStudyBook } from "./player/js/learn/index.js";
import { paintDeskLyrics } from "./desk/lyrics.js";

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
  openStudyBook,
  paintDeskLyrics
});
