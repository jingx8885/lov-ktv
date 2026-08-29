import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { roomUrl } from "../../origin.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { applyLyricMode, paintLine, cueIndexAt as cueIndexAtCues } from "../../../shared/lyrics/js/paint.js";
import { paintLyricMode } from "../../room/js/mix.js";
import { api } from "../../api.js";
import { state, LIB_LETTERS } from "../../state.js";
import { ICO, songLetter } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { setPlayerSheet, syncPlayerSheetMeta } from "./sheet.js";
import { nextSongId } from "./state.js";

export function mediaUrl(songId, name) {
  const song = state.playerSong;
  const rev = (song && (song.id === songId || song.song_id === songId) && song.media_rev)
    || state.songMediaRev
    || "";
  return `/media/${songId}/${name}` + (rev ? `?v=${encodeURIComponent(rev)}` : "");
}

export function setPlayIcon(playing) {
  const icon = playing ? ICO.pause : ICO.play;
  const label = playing ? t("common.pause") : t("common.play");
  ["playerPlay", "editPlay"].forEach((id) => {
    const btn = $(id);
    if (!btn) return;
    if (btn.getAttribute("aria-label") !== label) btn.innerHTML = icon;
    btn.setAttribute("aria-label", label);
    btn.classList.toggle("is-playing", !!playing);
  });
}

export function playerIsPlaying() {
  const audio = $("playerAudio");
  if (state.playerClockHold != null && !state.playerHeld) return true;
  return !!(audio && audio.src && !audio.paused);
}

export function refreshPlayIcon() {
  setPlayIcon(playerIsPlaying());
}

export function pausePlayerTracks() {
  state.playerHeld = true;
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  if (audio) audio.pause();
  if (guide) guide.pause();
  refreshPlayIcon();
}

export function unlockPlayerGesture() {
  state.playerHeld = false;
  const audio = $("playerAudio");
  if (!audio) return;
  hookPlayerAudio();
  audio.play().catch(() => {});
  const guide = $("playerGuide");
  if (guide && guide.getAttribute("src") && state.playerVocal) guide.play().catch(() => {});
}

export function togglePlayer() {
  if (!state.playerSong) return showToast(t("phone.player.needSong"));
  const audio = $("playerAudio");
  hookPlayerAudio();
  if (playerIsPlaying()) {
    pausePlayerTracks();
    applyPlayerVocalMix();
    return;
  }
  state.playerHeld = false;
  setPlayIcon(true);
  kickPlayerPaint();
  audio.play().then(() => {
    applyPlayerVocalMix();
    refreshPlayIcon();
  }).catch(() => {
    pausePlayerTracks();
    showToast(t("phone.player.needTap"));
  });
}

export function playFromMs(ms) {
  if (!state.playerSong) return;
  const audio = $("playerAudio");
  const start = () => {
    hookPlayerAudio();
    try { audio.currentTime = Math.max(0, ms) / 1000; } catch (err) {}
    syncGuide(Math.max(0, ms) / 1000);
    state.playerHeld = false;
    audio.play().then(() => {
      applyPlayerVocalMix();
      refreshPlayIcon();
    }).catch(() => refreshPlayIcon());
    if (!state.playerRaf) state.playerRaf = requestAnimationFrame(paintPlayer);
  };
  if (audio.readyState >= 1) start();
  else audio.addEventListener("loadedmetadata", start, { once: true });
}

export function pausePlayer() {
  pausePlayerTracks();
  if (state.playerRaf) {
    cancelAnimationFrame(state.playerRaf);
    state.playerRaf = 0;
  }
}

export function kickPlayerPaint() {
  if (state.playerRaf) return;
  const page = $("page-player");
  if (page && page.hidden) return;
  state.playerRaf = requestAnimationFrame(paintPlayer);
}

export function mediaAhead(el, at) {
  try {
    const ranges = el.buffered;
    const t = Number(at) || 0;
    for (let i = 0; i < ranges.length; i += 1) {
      if (t >= ranges.start(i) - 0.05 && t <= ranges.end(i)) return ranges.end(i) - t;
    }
  } catch (err) {}
  return 0;
}

export function applyKaraokeGain() {
  const editing = document.body.classList.contains("edit-on");
  const value = editing && !state.mixTrackOn ? 0 : 1;
  if (state.playerHook && state.playerHook.gain) state.playerHook.gain.gain.value = value;
}

export function syncGuide(forceTime) {
  const audio = $("playerAudio");
  const guide = $("playerGuide");
  if (!guide || !guide.getAttribute("src")) return;
  const editing = document.body.classList.contains("edit-on");
  const want = !state.playerHeld && !!(audio && audio.src) && (editing ? state.voiceTrackOn : !!state.playerVocal);
  const clock = forceTime != null ? forceTime : (audio.currentTime || 0);
  if (guide.readyState >= 1 && !guide.seeking) {
    const drift = Math.abs((guide.currentTime || 0) - clock);
    const slack = forceTime != null ? 0.08 : 0.32;
    const targetReady = forceTime != null || mediaAhead(guide, clock) > 0.2;
    if (drift > slack && targetReady) {
      try { guide.currentTime = clock; } catch (err) {}
    }
  }
  guide.muted = !want;
  if (want && audio && !audio.paused) {
    if (guide.paused) guide.play().catch(() => {});
  } else {
    guide.pause();
  }
}

export function applyPlayerVocalMix() {
  applyKaraokeGain();
  syncGuide();
}

export function hookPlayerAudio() {
  const ctx = api.ensurePhoneCtx();
  state.playerHook = LovBands.hookAnalyser($("playerAudio"), state.playerHook, ctx ? { ctx } : null);
  if (state.playerHook && state.playerHook.ctx && state.playerHook.ctx.state === "suspended") {
    state.playerHook.ctx.resume().catch(() => {});
  }
  if (state.playerHook && state.playerHook.ctx) state.phoneCtx = state.playerHook.ctx;
  applyKaraokeGain();
}

export function releasePlayerClock() {
  state.playerClockHold = null;
  state.playerClockHoldAt = 0;
}

export function fmtClock(ms) {
  const n = Math.max(0, Math.floor((ms || 0) / 1000));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}

export function setPlayerCover(song) {
  const art = $("playerArt");
  const cover = $("playerCover");
  art.classList.remove("has-cover");
  cover.hidden = true;
  cover.removeAttribute("src");
  if (!song || !song.id) return;
  cover.onload = () => {
    cover.hidden = false;
    art.classList.add("has-cover");
  };
  cover.onerror = () => {
    cover.hidden = true;
    cover.removeAttribute("src");
    art.classList.remove("has-cover");
  };
  cover.src = mediaUrl(song.id, "cover.jpg");
}

export function cueIndexAt(t) {
  return cueIndexAtCues(state.playerLyrics.cues || [], t);
}

export function updatePlayOrderBtns() {
  const shuffle = state.playOrder === "shuffle";
  const icon = shuffle ? ICO.shuffle : ICO.seq;
  const label = shuffle ? t("common.shuffle") : t("common.seq");
  const main = $("playerOrder");
  if (main) {
    main.innerHTML = `${icon}<em class="vh" id="playerOrderLabel">${label}</em>`;
    main.setAttribute("aria-label", shuffle ? t("common.shufflePlay") : t("common.seqPlay"));
    main.classList.toggle("on", shuffle);
  }
  const edit = $("playerOrderEdit");
  if (edit) {
    edit.innerHTML = icon;
    edit.setAttribute("aria-label", shuffle ? t("common.shufflePlay") : t("common.seqPlay"));
    edit.classList.toggle("on", shuffle);
  }
}

export function togglePlayOrder() {
  state.playOrder = state.playOrder === "shuffle" ? "seq" : "shuffle";
  localStorage.setItem("playOrder", state.playOrder);
  updatePlayOrderBtns();
}

export function renderPlayerIndex() {
  const nav = $("playerIndex");
  if (!nav) return;
  const have = new Set(state.playerCatalog.map((song) => song.letter || songLetter(song.title)));
  nav.innerHTML = LIB_LETTERS.map((key) => {
    const on = have.has(key);
    return `<button type="button" class="lib-letter" data-player-letter="${key}" ${on ? "" : "disabled"}>${key}</button>`;
  }).join("");
  nav.querySelectorAll("[data-player-letter]").forEach((btn) => {
    btn.onclick = () => {
      const row = $("playerList").querySelector(`[data-letter="${btn.dataset.playerLetter}"]`);
      if (row) row.scrollIntoView({ block: "start" });
    };
  });
}

export async function loadPlayerList() {
  const { data } = await fetchJson("/api/songs").catch(() => ({ data: { songs: [] } }));
  state.playerCatalog = (data.songs || []).filter((song) => song.status === "ready");
  renderPlayerList();
}

export function renderPlayerList() {
  const box = $("playerList");
  if (!box) return;
  const cur = state.playerSong && state.playerSong.id;
  box.innerHTML = state.playerCatalog.map((song) => `
        <button type="button" class="list-row player-pick${song.id === cur ? " on" : ""}" data-pick="${song.id}" data-letter="${escapeHtml(song.letter || songLetter(song.title))}">
          <span class="list-copy">
            <b>${escapeHtml(song.title)}</b>
            <span class="tiny">${escapeHtml(song.artist || "")}</span>
          </span>
        </button>
      `).join("") || `<div class="empty-state"><p>${t("phone.player.emptyLib")}</p></div>`;
  box.querySelectorAll("[data-pick]").forEach((btn) => {
    btn.onclick = () => {
      unlockPlayerGesture();
      setPlayerSheet("peek", true);
      loadPlayerSong(btn.dataset.pick, { play: true });
    };
  });
  syncPlayerSheetMeta();
  renderPlayerIndex();
  const on = box.querySelector(".player-pick.on");
  if (on) on.scrollIntoView({ block: "nearest" });
}

export function playNextSong() {
  const cur = state.playerSong && state.playerSong.id;
  const next = nextSongId(state.playerCatalog, cur, state.playOrder);
  if (!next) return;
  loadPlayerSong(next, { play: true });
}

export function drawPlayerBands(t) {
  if (!state.playerViz) state.playerViz = LovBands.create($("playerBands"));
  const audio = $("playerAudio");
  if (audio && (audio.currentSrc || audio.src)) state.playerViz.setSource(audio.currentSrc || audio.src);
  const playing = !!(state.playerHook && audio && !audio.paused && audio.src);
  if (playing) LovBands.pull(state.playerHook);
  state.playerViz.draw({
    playing,
    freq: state.playerHook && state.playerHook.freq,
    wave: state.playerHook && state.playerHook.time,
    playMs: t || 0,
    duration: (audio.duration || 0) * 1000,
    cues: state.playerLyrics.cues || [],
    selected: state.selectedCue,
  });
}

function playerIdleLyric() {
  return state.playerSong ? "" : t("phone.player.idle");
}

export function paintPlayer() {
  if ($("page-player").hidden) {
    state.playerRaf = 0;
    return;
  }
  const audio = $("playerAudio");
  const hold = state.playerClockHold;
  const t = Math.floor(((hold != null ? hold : (audio.currentTime || 0)) * 1000));
  const cues = state.playerLyrics.cues || [];
  const mode = applyLyricMode(document.body, state.lyricMode);
  const idx = cues.findIndex((c) => t >= c.start_ms && t < c.end_ms);
  const upcomingIdx = cues.findIndex((c) => t < c.start_ms);
  if (idx >= 0) {
    paintLine($("playerPrev"), idx > 0 ? cues[idx - 1] : null, 1e12, "prev", state.lyricPaint, "", mode);
    paintLine($("playerCur"), cues[idx], t, "cur", state.lyricPaint, "", mode);
    paintLine($("playerNext"), cues[idx + 1] || null, -1, "next", state.lyricPaint, "", mode);
  } else if (upcomingIdx >= 0) {
    const held = upcomingIdx > 0 ? cues[upcomingIdx - 1] : null;
    paintLine($("playerPrev"), upcomingIdx > 1 ? cues[upcomingIdx - 2] : null, 1e12, "prev", state.lyricPaint, "", mode);
    paintLine($("playerCur"), held, held ? 1e12 : 0, "cur", state.lyricPaint, "", mode);
    paintLine($("playerNext"), cues[upcomingIdx], -1, "next", state.lyricPaint, "", mode);
  } else {
    paintLine($("playerPrev"), cues.length ? cues[cues.length - 1] : null, 1e12, "prev", state.lyricPaint, "", mode);
    paintLine($("playerCur"), null, 0, "cur", state.lyricPaint, playerIdleLyric(), mode);
    paintLine($("playerNext"), null, 0, "next", state.lyricPaint, "", mode);
  }
  const dragging = !!(state.alignTl && state.alignTl.isDragging());
  const nextSel = cueIndexAt(t);
  if (nextSel !== state.selectedCue && !dragging) {
    state.selectedCue = nextSel;
  }
  if (document.body.classList.contains("edit-on")) api.updateAlignNow(t);
  drawPlayerBands(t);
  const durSec = (Number.isFinite(audio.duration) && audio.duration > 0) ? audio.duration : state.playerHoldDur;
  const dur = (durSec || 0) * 1000;
  $("playerNow").textContent = fmtClock(t);
  $("playerLeft").textContent = dur ? `−${fmtClock(Math.max(0, dur - t))}` : "−0:00";
  const seek = $("playerSeek");
  if (seek) {
    const ratio = durSec ? Math.max(0, Math.min(1, (t / 1000) / durSec)) : 0;
    if (!seek.matches(":active") && durSec) seek.value = String(Math.round(ratio * 1000));
    seek.style.setProperty("--seek-p", `${(seek.matches(":active") ? Number(seek.value) / 1000 : ratio) * 100}%`);
  }
  $("playerArt").classList.toggle("is-live", (!audio.paused || state.playerClockHold != null) && !!audio.src && !state.playerHeld);
  refreshPlayIcon();
  if (hold != null) {
    syncGuide(hold);
  } else {
    syncGuide();
  }
  if (!$("playerAlign").hidden) {
    api.ensureTimeline().sync(t, dur);
  }
  state.playerRaf = requestAnimationFrame(paintPlayer);
}

export function mediaPath(src) {
  try { return new URL(src, location.href).pathname; } catch (err) { return String(src || "").split("?")[0]; }
}

export function resetPlayerFace() {
  releasePlayerClock();
  state.playerHoldDur = 0;
  state.selectedCue = 0;
  state.lyricPaint.prev = "";
  state.lyricPaint.cur = "";
  state.lyricPaint.next = "";
  state.lyricPaint.align = "";
  $("playerPrev").textContent = "";
  $("playerCur").textContent = "";
  $("playerNext").textContent = "";
  $("playerNow").textContent = "0:00";
  $("playerLeft").textContent = "−0:00";
  if (state.playerViz) state.playerViz.draw({ playing: false, playMs: 0, duration: 0, cues: [], selected: 0 });
}

export function waitMedia(el, gen, wantSrc) {
  return new Promise((resolve) => {
    if (!el || !el.getAttribute("src")) {
      resolve(false);
      return;
    }
    const want = mediaPath(wantSrc || el.getAttribute("src"));
    const isNew = () => el.readyState >= 1 && mediaPath(el.currentSrc || el.src) === want;
    if (isNew()) {
      resolve(true);
      return;
    }
    const finish = (ok) => {
      el.removeEventListener("loadedmetadata", onOk);
      el.removeEventListener("error", onErr);
      resolve(ok);
    };
    const onOk = () => finish(gen === state.playerLoad && isNew());
    const onErr = () => finish(false);
    el.addEventListener("loadedmetadata", onOk);
    el.addEventListener("error", onErr, { once: true });
    if (isNew()) finish(true);
    else setTimeout(() => { if (isNew()) finish(true); }, 0);
  });
}

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
  try { audio.currentTime = 0; } catch (err) {}
  try { if (guide) guide.currentTime = 0; } catch (err) {}
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
  guide.src = guideUrl;
  guide.load();
  guide.onerror = () => {
    if (gen !== state.playerLoad) return;
    guide.removeAttribute("src");
    guide.load();
  };
  api.ensureTimeline().setVoiceUrl(guideUrl);
  api.applyEditorTracks();
  api.renderAlignList();
  renderPlayerList();
  const ready = await waitMedia(audio, gen, karaoke);
  if (gen !== state.playerLoad) return;
  try { audio.currentTime = 0; } catch (err) {}
  try { if (guide.getAttribute("src") && guide.readyState >= 1) guide.currentTime = 0; } catch (err) {}
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
  if (!state.playerRaf) state.playerRaf = requestAnimationFrame(paintPlayer);
}

export function openPlayer(songId) {
  unlockPlayerGesture();
  api.showPage("player", songId);
}

export async function bootPlayer() {
  if (!state.playerRaf) state.playerRaf = requestAnimationFrame(paintPlayer);
  if (state.playerSong) return;
  const code = $("room").value.trim();
  if (!code) return;
  const roomHit = await fetchJson(roomUrl("/api/rooms/" + code)).catch(() => null);
  const room = roomHit && roomHit.data;
  if (room && room.now_playing && room.now_playing.status === "ready") {
    await loadPlayerSong(room.now_playing.song_id);
  }
}

export function seekPlayerRatio(ratio) {
  const audio = $("playerAudio");
  if (!audio.duration) return;
  audio.currentTime = Math.max(0, Math.min(1, ratio)) * audio.duration;
  syncGuide(audio.currentTime);
}

export function bindPlayback() {
  $("playerPlay").onclick = () => togglePlayer();
  ["play", "pause", "ended"].forEach((name) => {
    $("playerAudio").addEventListener(name, refreshPlayIcon);
  });
  $("playerVocal").onclick = () => {
    state.playerVocal = state.playerVocal ? 0 : 1;
    localStorage.setItem("playerVocal", state.playerVocal ? "1" : "0");
    $("playerVocal").classList.toggle("on", !!state.playerVocal);
    $("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
    $("playerVocal").setAttribute("aria-label", state.playerVocal ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff"));
    releasePlayerClock();
    applyPlayerVocalMix();
  };
  $("playerSeek").addEventListener("input", () => {
    const ratio = Number($("playerSeek").value) / 1000;
    $("playerSeek").style.setProperty("--seek-p", `${ratio * 100}%`);
    seekPlayerRatio(ratio);
  });
  $("playerAudio").onended = () => {
    if (document.body.classList.contains("learn-on")) return;
    if (state.playerClockHold != null) return;
    const audio = $("playerAudio");
    const dur = audio.duration;
    const t = audio.currentTime || 0;
    if (!Number.isFinite(dur) || dur < 0.5) return;
    if (t < dur * 0.95 && t < dur - 0.35) return;
    playNextSong();
  };
  $("playerVocal").classList.toggle("on", !!state.playerVocal);
  $("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
  $("playerVocal").setAttribute("aria-label", state.playerVocal ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff"));
  $("playerOrder").onclick = () => togglePlayOrder();
  $("playerNextBtn").onclick = () => playNextSong();
  updatePlayOrderBtns();
  $("playerToDesk").onclick = () => {
    api.showPage("desk");
  };
}

