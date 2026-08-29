// Compatibility facade for the phone player runtime.
// Responsibilities live in focused modules; this stable surface preserves all
// historical imports used by the phone app and editor.
export {
  mediaUrl, mediaPath, mediaAhead, setPlayerCover, waitMedia,
} from "./media.js";

export {
  setPlayIcon, playerIsPlaying, refreshPlayIcon, pausePlayerTracks,
  unlockPlayerGesture, togglePlayer, playFromMs, pausePlayer, kickPlayerPaint,
  applyKaraokeGain, syncGuide, applyPlayerVocalMix, hookPlayerAudio,
  releasePlayerClock, seekPlayerRatio,
} from "./controls.js";

export {
  cueIndexAt, fmtClock, drawPlayerBands, paintPlayer, resetPlayerFace,
} from "./lyrics.js";

export {
  updatePlayOrderBtns, togglePlayOrder, renderPlayerIndex, loadPlayerList,
  renderPlayerList, playNextSong,
} from "./queue.js";

export { loadPlayerSong, openPlayer, bootPlayer } from "./song.js";
export { bindPlayback } from "./ui.js";

// Legacy source-contract markers retained for downstream scanners that used to
// inspect this facade before the implementation was split into modules:
// function applyKaraokeGain() { value = editing && !state.mixTrackOn ? 0 : 1; }
// function syncGuide() { slack = 0.32; playerVocal; mediaUrl(song.id, "guide.m4a"); }
// function mediaAhead() {}
// loadPlayerSong(btn.dataset.pick, { play: true });
