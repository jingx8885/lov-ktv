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
  editSong,
  ensureTimeline,
  updateAlignNow,
  renderAlignList,
  applyEditorTracks,
  syncEditAxis,
  syncEditEntry
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
import { loadPlayerList, playNextSong, renderPlayerSources, selectPlayerSource, toggleCurrentFavorite } from "./player/js/playback/queue.js";
import { openPlaylistSheet, refreshPlaylists } from "./player/js/playback/playlists.js";
import { loadPlayerSong, openPlayer, bootPlayer } from "./player/js/playback/song.js";
import { ensureGuideLoaded, ensureMtvLoaded, releasePlayerMtv } from "./player/js/playback/media.js";
import { cueIndexAt } from "./player/js/playback/lyrics.js";
import { setPlayerSheet, syncPlayerSheetMeta } from "./player/js/playback/sheet.js";
import {
  enterLearn,
  enterCover,
  exitLearn,
  openRecite,
  openSongWords,
  openStudyBook,
  syncLearnLyricMode
} from "./player/js/learn/index.js";
import { paintDeskLyrics } from "./desk/js/lyrics.js";

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
  editSong,
  ensureTimeline,
  updateAlignNow,
  renderAlignList,
  applyEditorTracks,
  syncEditAxis,
  syncEditEntry,
  setPlayIcon,
  refreshPlayIcon,
  unlockPlayerGesture,
  togglePlayer,
  playFromMs,
  pausePlayer,
  applyKaraokeGain,
  syncGuide,
  ensureGuideLoaded,
  ensureMtvLoaded,
  releasePlayerMtv,
  applyPlayerVocalMix,
  hookPlayerAudio,
  loadPlayerList,
  renderPlayerSources,
  selectPlayerSource,
  toggleCurrentFavorite,
  openPlaylistSheet,
  refreshPlaylists,
  loadPlayerSong,
  openPlayer,
  bootPlayer,
  playNextSong,
  cueIndexAt,
  setPlayerSheet,
  syncPlayerSheetMeta,
  enterLearn,
  enterCover,
  exitLearn,
  openStudyBook,
  openRecite,
  openSongWords,
  paintDeskLyrics,
  syncLearnLyricMode
});
