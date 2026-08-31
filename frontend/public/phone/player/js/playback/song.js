import { $ } from "../../../../shared/ui/js/dom.js";
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
  syncGuide,
  unlockPlayerGesture
} from "./controls.js";
import { mediaUrl, waitMedia, setPlayerCover } from "./media.js";
import { sanitizeLyrics } from "../../../../shared/lyrics/js/paint.js";
import { kickPlayerPaint, resetPlayerFace } from "./lyrics.js";
import { markCurrentPlayerPick, renderPlayerList } from "./queue.js";
import { paintDeskLyrics } from "../../../desk/lyrics.js";

export async function loadPlayerSong(songId, opts) {
  const wantPlay = !!(opts && opts.play);
  const gen = ++state.playerLoad;
  /** @type {{ data: Song }} */
  const { data: song } = await fetchJson("/api/songs/" + songId);
  if (gen !== state.playerLoad) return;
  if (!song.id || song.status !== "ready") {
    $("playerMeta").textContent = t("phone.player.notReady");
    return;
  }
  api.stopPreview();
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  const mtv = $("playerMtv");
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
  state.playerLyrics = { cues: [] };
  resetPlayerFace();
  try {
    audio.currentTime = 0;
  } catch (err) {}
  try {
    if (guide) guide.currentTime = 0;
  } catch (err) {}
  const lyrics = await fetchJson(mediaUrl(song.id, "lyrics.json"));
  state.playerLyrics = lyrics.ok ? sanitizeLyrics(lyrics.data) : { cues: [] };
  paintDeskLyrics();
  paintLyricMode(state.lyricMode, song.language || state.playerLyrics.language || "");
  if (gen !== state.playerLoad) return;
  state.lyricsDirty = false;
  resetPlayerFace();
  $("playerTitle").textContent = song.title;
  $("playerMeta").textContent = song.artist && !String(song.title).includes(song.artist) ? song.artist : "";
  setPlayerCover(song);
  $("playerVocal").classList.toggle("on", !!state.playerVocal);
  $("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
  state.songMediaRev = song.media_rev || "";
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
      mtv.removeAttribute("src");
      mtv.load();
    };
    mtv.onloadeddata = () => {
      if (gen !== state.playerLoad) return;
      mtv.hidden = !document.body.classList.contains("display-mv");
      try {
        mtv.currentTime = 0;
      } catch (err) {}
    };
    mtv.src = mediaUrl(song.id, "mtv.mp4");
    mtv.load();
  }
  api.ensureTimeline().setVoiceUrl(guideUrl);
  api.applyEditorTracks();
  api.renderAlignList();
  if (opts?.refreshPlayerCatalog === false) markCurrentPlayerPick(song.id);
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
      setPlayIcon(true);
      syncGuide(0);
      applyPlayerVocalMix();
    } catch (err) {
      state.playerHeld = true;
      setPlayIcon(false);
    }
  } else {
    state.playerHeld = true;
    setPlayIcon(false);
    applyPlayerVocalMix();
  }
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
