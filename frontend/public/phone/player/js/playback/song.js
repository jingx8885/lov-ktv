import { $ } from "../../../../shared/ui/js/dom.js";
import { songArtist, songTitle } from "../../../../shared/ui/js/song.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { roomUrl } from "../../../origin.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { paintLyricMode } from "../../../room/js/room/mix.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import {
  applyPlayerVocalMix,
  hookPlayerAudio,
  playerTrackName,
  setPlayIcon,
  setPlayerLoading,
  syncGuide,
  unlockPlayerGesture
} from "./controls.js";
import { mediaUrl, waitMedia, setPlayerCover } from "./media.js";
import { sanitizeLyrics } from "../../../../shared/lyrics/js/paint.js";
import { kickPlayerPaint, resetPlayerFace } from "./lyrics.js";
import { markCurrentPlayerPick, renderPlayerList } from "./queue.js";
import { paintDeskLyrics } from "../../../desk/js/lyrics.js";
import { syncPlayerSheetMeta } from "./sheet.js";

export async function loadPlayerSong(songId, opts) {
  const wantPlay = !!(opts && opts.play);
  const gen = ++state.playerLoad;
  setPlayerLoading(true);
  /** @type {Song} */
  let song;
  try {
    const result = await fetchJson("/api/songs/" + songId);
    song = result.data;
  } catch (err) {
    if (gen === state.playerLoad) setPlayerLoading(false);
    return;
  }
  if (gen !== state.playerLoad) return;
  if (!song.id || song.status !== "ready") {
    $("playerMeta").textContent = t("phone.player.notReady");
    setPlayerLoading(false);
    return;
  }
  api.stopPreview();
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  const mtv = $("playerMtv");
  const art = $("playerArt");
  audio.pause();
  if (guide) guide.pause();
  if (mtv) {
    mtv.pause();
    mtv.hidden = true;
    mtv.onerror = null;
    mtv.onloadeddata = null;
    mtv.removeAttribute("src");
    mtv.load();
  }
  audio.onloadedmetadata = null;
  audio.onerror = null;
  if (guide) {
    guide.onloadedmetadata = null;
    guide.onerror = null;
  }
  state.playerSong = song;
  // 空闲页不显示封面/进度占位；歌曲资料确认可用后再恢复播放器舞台。
  const playerStage = $("playerStage");
  if (playerStage) playerStage.hidden = false;
  const playerClockDock = $("playerClockDock");
  if (playerClockDock) playerClockDock.hidden = false;
  state.playerLyrics = { cues: [] };
  resetPlayerFace();
  try {
    audio.currentTime = 0;
  } catch (err) {}
  try {
    if (guide) guide.currentTime = 0;
  } catch (err) {}
  state.songMediaRev = song.media_rev || "";
  // Start the lyrics request in parallel; it should not block audio startup.
  const lyricsPromise = fetchJson(mediaUrl(song.id, "lyrics.json")).catch(() => ({ ok: false, data: null }));
  $("playerTitle").textContent = songTitle(song);
  $("playerMeta").textContent = songArtist(song);
  syncPlayerSheetMeta();
  setPlayerCover(song);
  $("playerVocal").classList.toggle("on", !!state.playerVocal);
  $("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
  const karaoke = mediaUrl(song.id, "karaoke.m4a");
  const original = mediaUrl(song.id, "original.mp3");
  const selected = mediaUrl(song.id, playerTrackName());
  audio.src = selected;
  audio.load();
  audio.onerror = () => {
    if (gen !== state.playerLoad) return;
    if (String(audio.currentSrc || audio.src).includes("original.mp3")) {
      audio.src = karaoke;
      audio.load();
    }
  };
  const guideUrl = mediaUrl(song.id, "guide.m4a");
  if (guide) {
    guide.src = guideUrl;
    guide.load();
    guide.onerror = () => {
      if (gen !== state.playerLoad) return;
      guide.removeAttribute("src");
      guide.load();
    };
  }
  if (mtv) {
    mtv.onerror = () => {
      if (gen !== state.playerLoad) return;
      mtv.hidden = true;
      if (art) art.classList.remove("has-mtv");
      mtv.removeAttribute("src");
      mtv.load();
    };
    mtv.onloadeddata = () => {
      if (gen !== state.playerLoad) return;
      mtv.hidden = !document.body.classList.contains("display-mv");
      if (art) art.classList.toggle("has-mtv", document.body.classList.contains("display-mv"));
      const fullscreen = $("playerFullscreen");
      if (fullscreen) fullscreen.hidden = !document.body.classList.contains("display-mv");
      try {
        mtv.currentTime = 0;
      } catch (err) {}
    };
    mtv.src = mediaUrl(song.id, "mtv.mp4");
    // Reserve the shared MV/lyrics grid as soon as a new video source is
    // selected, instead of briefly rendering the compact progress-row layout
    // while the first frame is decoding.
    if (art) art.classList.toggle("has-mtv", document.body.classList.contains("display-mv"));
    mtv.load();
  }
  api.ensureTimeline().setVoiceUrl(guideUrl);
  api.applyEditorTracks();
  api.renderAlignList();
  // Selecting a song from the already-rendered catalog only needs to move the
  // highlight. Rebuilding hundreds of rows here makes a manual track switch
  // feel sluggish on mobile WebViews.
  if (opts?.refreshPlayerCatalog === false || state.playerCatalog.length) markCurrentPlayerPick(song.id);
  else renderPlayerList();
  const ready = await waitMedia(audio, gen, selected);
  if (gen !== state.playerLoad) return;
  try {
    audio.currentTime = 0;
  } catch (err) {}
  try {
    if (guide && guide.getAttribute("src") && guide.readyState >= 1) guide.currentTime = 0;
  } catch (err) {}
  hookPlayerAudio();
  api.ensureTimeline().render();
  if (ready && wantPlay) {
    state.playerHeld = false;
    try {
      await audio.play();
      setPlayerLoading(false);
      setPlayIcon(true);
      syncGuide(0);
      applyPlayerVocalMix();
    } catch (err) {
      setPlayerLoading(false);
      state.playerHeld = true;
      setPlayIcon(false);
    }
  } else {
    setPlayerLoading(false);
    state.playerHeld = true;
    setPlayIcon(false);
    applyPlayerVocalMix();
  }
  kickPlayerPaint();

  // Lyrics can arrive after playback has started without delaying the first beat.
  const lyrics = await lyricsPromise;
  if (gen !== state.playerLoad) return;
  state.playerLyrics = lyrics.ok ? sanitizeLyrics(lyrics.data) : { cues: [] };
  state.lyricsDirty = false;
  paintDeskLyrics();
  paintLyricMode(state.lyricMode, song.language || state.playerLyrics.language || "");
  kickPlayerPaint();
}

export function openPlayer(songId) {
  unlockPlayerGesture();
  api.showPage("player", songId);
}

export async function bootPlayer() {
  kickPlayerPaint();
  // 学习中心会自行选择歌曲，避免进入学习页时房间当前歌曲抢先加载。
  if (document.body.classList.contains("learn-on")) return;
  if (state.playerSong) return;
  const code = $("room")?.value.trim();
  if (!code) return;
  const roomHit = await fetchJson(roomUrl("/api/rooms/" + code)).catch(() => null);
  const room = roomHit && roomHit.data;
  if (room && room.now_playing && room.now_playing.status === "ready") {
    await loadPlayerSong(room.now_playing.song_id);
  }
}
