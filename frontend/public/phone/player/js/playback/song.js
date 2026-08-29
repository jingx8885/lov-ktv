import { $ } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { roomUrl } from "../../../origin.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { paintLyricMode } from "../../../room/js/room/mix.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { applyPlayerVocalMix, hookPlayerAudio, setPlayIcon, syncGuide, unlockPlayerGesture } from "./controls.js";
import { mediaUrl, waitMedia, setPlayerCover } from "./media.js";
import { kickPlayerPaint, resetPlayerFace } from "./lyrics.js";
import { renderPlayerList } from "./queue.js";

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
  audio.pause();
  if (guide) guide.pause();
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
  state.playerLyrics = lyrics.ok ? lyrics.data : { cues: [] };
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
  audio.src = karaoke;
  audio.load();
  audio.onerror = () => {
    if (gen !== state.playerLoad) return;
    if (!String(audio.currentSrc || audio.src).includes("original.mp3")) {
      audio.src = original;
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
  api.ensureTimeline().setVoiceUrl(guideUrl);
  api.applyEditorTracks();
  api.renderAlignList();
  renderPlayerList();
  const ready = await waitMedia(audio, gen, karaoke);
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
  if (state.playerSong) return;
  const code = $("room")?.value.trim();
  if (!code) return;
  const roomHit = await fetchJson(roomUrl("/api/rooms/" + code)).catch(() => null);
  const room = roomHit && roomHit.data;
  if (room && room.now_playing && room.now_playing.status === "ready") {
    await loadPlayerSong(room.now_playing.song_id);
  }
}
