import { t } from "../../../shared/i18n/js/i18n.js";
import { $ } from "../../../shared/ui/js/dom.js";
import { state } from "../../state.js";

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

export function roomLine(snap) {
  const mix = Math.round(((snap && snap.vocal_mix) || 0) * 100);
  const vol = snap && snap.volume != null ? snap.volume : 80;
  const n = ((snap && snap.queue) || []).length;
  const mic = snap && snap.mic_on ? t("tv.queueMic") : "";
  return t("tv.queue", { n, mix, vol }) + mic;
}

export function applyMix() {
  const mix = state.room && state.room.vocal_mix != null ? state.room.vocal_mix : 1;
  const hostMac = state.room && state.room.host_volume_kind === "mac";
  const vol = hostMac ? 1 : ((state.room && state.room.volume) != null ? state.room.volume : 80) / 100;
  const micGain = ((state.room && state.room.mic_gain) != null ? state.room.mic_gain : 80) / 100;
  const karaoke = $("karaoke");
  const vocal = $("vocal");
  const live = $("liveMic");
  karaoke.muted = mix >= 0.99;
  vocal.muted = mix <= 0.01;
  karaoke.volume = karaoke.muted ? 0 : vol * (1 - mix);
  vocal.volume = vocal.muted ? 0 : vol * mix;
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

export function syncVocal(forceTime) {
  const karaoke = $("karaoke");
  const vocal = $("vocal");
  const mix = state.room && state.room.vocal_mix != null ? state.room.vocal_mix : 1;
  if (!vocal || !vocal.getAttribute("src")) return;
  if (mix <= 0.01 && forceTime == null) {
    if (!vocal.paused) vocal.pause();
    return;
  }
  if (vocal.readyState < 1) return;
  const t = forceTime != null ? forceTime : karaoke.currentTime || 0;
  const now = Date.now();
  if (forceTime == null && now - state.lastVocalSync < 400) return;
  state.lastVocalSync = now;
  try {
    if (Math.abs((vocal.currentTime || 0) - t) > 0.35) vocal.currentTime = t;
  } catch (err) {}
  if (karaoke && !karaoke.paused && karaoke.src) {
    vocal.play().catch(() => {});
  } else {
    vocal.pause();
  }
}
