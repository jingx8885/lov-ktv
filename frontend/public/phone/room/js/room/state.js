import { fetchJson } from "../../../../shared/ui/js/http.js";
import { roomUrl } from "../../../origin.js";

/** @param {Room | null | undefined} room */
export function roomStamp(room) {
  return JSON.stringify({
    code: room && room.code,
    idx: room && room.now_index,
    mix: room && room.vocal_mix,
    vol: room && room.volume,
    paused: room && room.paused,
    // Lyric display is room-wide state.  Keep it in the polling fingerprint
    // so a mode change made by another client is not mistaken for an
    // unchanged room snapshot.
    lyric_mode: room && room.lyric_mode,
    display_mode: room && room.display_mode,
    now: room && room.now_playing && (room.now_playing.id || room.now_playing.song_id),
    nowStatus: room && room.now_playing && room.now_playing.status,
    q: (room && room.queue ? room.queue : []).map((item) => [item.id, item.song_id, item.status, item.title])
  });
}

/** @param {string} code */
export async function fetchRoom(code) {
  return fetchJson(roomUrl(`/api/rooms/${code}`)).catch(() => ({ ok: false, data: {} }));
}
