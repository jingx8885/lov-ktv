import { fetchJson } from "../../../../shared/ui/js/http.js";

let roomWs = null;
let roomWsCode = "";
let roomWsRetry = 0;
let roomWsTimer = 0;
let roomWsStamp = "";

export function snapshotStamp(room) {
  if (!room) return "";
  return JSON.stringify({
    code: room.code,
    now: room.now_playing && [
      room.now_playing.id,
      room.now_playing.song_id,
      room.now_playing.status,
      room.now_playing.media_rev,
      room.now_playing.title,
      room.now_playing.artist,
      room.now_playing.language
    ],
    paused: room.paused,
    mix: room.vocal_mix,
    volume: room.volume,
    mic: room.mic_on,
    lyric_mode: room.lyric_mode,
    display_mode: room.display_mode,
    queue: (room.queue || []).map((item) => [
      item.id,
      item.song_id,
      item.status,
      item.media_rev,
      item.title,
      item.artist
    ])
  });
}

export function roomWsLive() {
  return !!(roomWs && roomWs.readyState === 1);
}

/**
 * Keep room WebSocket lifecycle separate from playback application. The
 * callback receives only validated snapshot payloads; audio/UI side effects
 * remain in the caller.
 */
export function watchRoom(code, onRoom) {
  const next = String(code || "")
    .trim()
    .toUpperCase();
  if (!next) return;
  if (roomWs && roomWsCode === next && roomWs.readyState <= 1) return;
  closeRoomWs();
  roomWsCode = next;
  roomWsStamp = "";
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  let sock;
  try {
    sock = new WebSocket(proto + "//" + location.host + "/ws/rooms/" + encodeURIComponent(next));
  } catch (err) {
    return;
  }
  roomWs = sock;
  sock.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg && msg.type === "snapshot" && msg.room && typeof onRoom === "function") {
        const stamp = snapshotStamp(msg.room);
        if (stamp === roomWsStamp) return;
        roomWsStamp = stamp;
        onRoom(msg.room);
      }
    } catch (err) {}
  };
  sock.onopen = () => {
    roomWsRetry = 0;
  };
  sock.onclose = () => {
    if (roomWs !== sock) return;
    roomWs = null;
    const wait = Math.min(4000, 400 + roomWsRetry * 400);
    roomWsRetry += 1;
    roomWsTimer = window.setTimeout(() => watchRoom(next, onRoom), wait);
  };
}

export function closeRoomWs() {
  if (roomWsTimer) {
    clearTimeout(roomWsTimer);
    roomWsTimer = 0;
  }
  const sock = roomWs;
  roomWs = null;
  roomWsCode = "";
  roomWsStamp = "";
  if (!sock) return;
  try {
    sock.onclose = null;
    sock.close();
  } catch (err) {}
}

/** @param {string} code */
export function fetchRoomSnapshot(code) {
  const next = String(code || "")
    .trim()
    .toUpperCase();
  if (!next) return Promise.resolve({ ok: false, data: null });
  return fetchJson("/api/rooms/" + encodeURIComponent(next));
}
