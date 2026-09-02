import { t } from "../../../../shared/i18n/js/i18n.js";
import { $ } from "../../../../shared/ui/js/dom.js";
import { state } from "../../../state.js";

export function mediaRevFor(songId) {
  const snap = state.room;
  const now = snap && snap.now_playing;
  if (now && now.song_id === songId && now.media_rev) return String(now.media_rev);
  const hit = ((snap && snap.queue) || []).find((item) => item && item.song_id === songId);
  return hit && hit.media_rev ? String(hit.media_rev) : "";
}

export function mediaUrl(songId, name) {
  const rev = mediaRevFor(songId);
  return `/media/${songId}/${name}` + (rev ? `?v=${encodeURIComponent(rev)}` : "");
}

export function prefetchUrl(url) {
  if (!url || state.prefetched.has(url)) return;
  if (state.prefetchBusy >= 2) {
    if (!state.prefetchWait.includes(url)) state.prefetchWait.push(url);
    return;
  }
  state.prefetched.add(url);
  state.prefetchBusy += 1;
  fetch(url, { cache: "force-cache", credentials: "same-origin" })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        state.prefetched.delete(url);
        return;
      }
      const reader = res.body.getReader();
      while (true) {
        const step = await reader.read();
        if (step.done) break;
      }
    })
    .catch(() => {
      state.prefetched.delete(url);
    })
    .finally(() => {
      state.prefetchBusy = Math.max(0, state.prefetchBusy - 1);
      const next = state.prefetchWait.shift();
      if (next) prefetchUrl(next);
    });
}

export function prefetchQueue(snap) {
  const seen = new Set();
  const urls = [];
  const add = (songId) => {
    if (!songId || seen.has(songId)) return;
    seen.add(songId);
    urls.push(mediaUrl(songId, "karaoke.m4a"));
    urls.push(mediaUrl(songId, "mtv.mp4"));
    urls.push(mediaUrl(songId, "original.mp3"));
    urls.push(mediaUrl(songId, "lyrics.json"));
    urls.push(mediaUrl(songId, "skeleton.json"));
  };
  const now = snap && snap.now_playing;
  const nowId = now && now.status === "ready" ? now.song_id : "";
  ((snap && snap.queue) || []).forEach((item) => {
    if (item && item.status === "ready" && item.song_id !== nowId) add(item.song_id);
  });
  urls.slice(0, 12).forEach(prefetchUrl);
}

/** Song id embedded in a `/media/<songId>/<name>` URL. */
export function trackSongId(src) {
  const hit = /\/media\/([^/?#]+)\//.exec(String(src || ""));
  return hit ? hit[1] : "";
}

/** Song id of whatever the audio element currently holds. */
export function elementSongId(el) {
  return trackSongId((el && (el.getAttribute("src") || el.currentSrc || el.src)) || "");
}

function nowSongId() {
  const now = state.room && state.room.now_playing;
  return (now && now.song_id) || "";
}

/** The track the room asked for, ignoring any per-song degrade. */
export function roomTrackName() {
  const mix = state.room && state.room.vocal_mix != null ? state.room.vocal_mix : 1;
  return Number(mix) > 0.5 ? "original.mp3" : "karaoke.m4a";
}

/**
 * A song whose requested track failed to load is pinned to the other track.
 * Without the pin, every room snapshot flipped the source back and the song
 * bounced between original and backing until one of them happened to load.
 */
export function trackFallbackActive(songId) {
  const id = songId || nowSongId();
  return !!(id && state.fallbackSong === id && state.fallbackTrack);
}

export function markTrackFallback(songId, track) {
  if (!songId || !track) return;
  state.fallbackSong = songId;
  state.fallbackTrack = track;
}

export function clearTrackFallback(songId) {
  if (songId && state.fallbackSong !== songId) return;
  state.fallbackSong = "";
  state.fallbackTrack = "";
}

export function activeTrackName(songId) {
  const id = songId || nowSongId();
  if (trackFallbackActive(id)) return state.fallbackTrack;
  return roomTrackName();
}

/** Load exactly one playback track and keep the clock when toggling. */
export function ensureActiveTrack(songId, preserveTime = true) {
  const audio = $("karaoke");
  if (!audio || !songId) return false;
  const name = activeTrackName(songId);
  const url = mediaUrl(songId, name);
  if (audio.getAttribute("src") === url) return false;
  // Carrying the clock across a song change would start the next song part
  // way in. Only an original/backing swap of the same song keeps its time.
  const sameSong = elementSongId(audio) === songId;
  const time = preserveTime && sameSong ? Number(audio.currentTime) || 0 : 0;
  const wasPlaying = !audio.paused && !audio.ended;
  audio.pause();
  audio.dataset.track = name;
  audio.src = url;
  audio.load();
  audio.addEventListener(
    "loadedmetadata",
    () => {
      if (time > 0) {
        try {
          audio.currentTime = time;
        } catch (err) {}
      }
      if (wasPlaying) audio.play().catch(() => {});
    },
    { once: true }
  );
  return true;
}

export function roomLine(snap) {
  const mix = Math.round(((snap && snap.vocal_mix) || 0) * 100);
  const vol = snap && snap.volume != null ? snap.volume : 80;
  const n = ((snap && snap.queue) || []).length;
  const mic = snap && snap.mic_on ? t("tv.queueMic") : "";
  return t("tv.queue", { n, mix, vol }) + mic;
}

export function applyMix() {
  const hostMac = state.room && state.room.host_volume_kind === "mac";
  const vol = hostMac ? 1 : ((state.room && state.room.volume) != null ? state.room.volume : 80) / 100;
  const micGain = ((state.room && state.room.mic_gain) != null ? state.room.mic_gain : 80) / 100;
  const karaoke = $("karaoke");
  const live = $("liveMic");
  const now = state.room && state.room.now_playing;
  if (now && now.status === "ready") ensureActiveTrack(now.song_id);
  karaoke.muted = false;
  karaoke.volume = vol;
  const g = Math.max(0, Math.min(1, vol * micGain));
  const filtered = !!(window.LovAec && LovAec.isActive());
  if (filtered) LovAec.setGain(g);
  if (live) {
    live.muted = filtered;
    live.volume = filtered ? 0 : g;
    if (!filtered && live.srcObject && live.paused) live.play().catch(() => {});
  }
  $("micLive").hidden = !(state.room && state.room.mic_on) && !state.pendingMic;
  $("qinfo").textContent = roomLine(state.room);
}
