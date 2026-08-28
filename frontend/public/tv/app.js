import "./install.js";
import { $must } from "../shared/ui/js/dom.js";
import { fetchJson } from "../shared/ui/js/http.js";
import { state } from "./state.js";
import { bootAuth, roomCode } from "./auth/js/login.js";
import { unlockAudio } from "./audio/js/unlock.js";
import { bindRoomRtc } from "./audio/js/mic.js";
import { applyMix } from "./playback/js/mix.js";
import { tick, startPlayback, stopPlayback, pauseAudio, pageVisible } from "./playback/js/tick.js";
import { paint } from "./playback/js/lyrics.js";

if (state.audioBus) {
  state.audioBus.onmessage = (event) => {
    if (event.data && event.data.type === "claim" && event.data.tabId !== state.tabId && state.isLeader) {
      state.isLeader = false;
      pauseAudio();
    }
  };
}
document.addEventListener("visibilitychange", () => {
  if (!pageVisible()) {
    pauseAudio();
    return;
  }
  if (state.armed && state.room && state.room.now_playing) startPlayback();
});

$must("start").onclick = () => {
  unlockAudio();
  startPlayback();
};
document.addEventListener("pointerdown", () => {
  unlockAudio();
  const karaoke = $must("karaoke");
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && karaoke.paused) {
    startPlayback();
  }
});
document.addEventListener("keydown", () => {
  unlockAudio();
  const karaoke = $must("karaoke");
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && karaoke.paused) {
    startPlayback();
  }
});
$must("skip").onclick = async () => {
  const code = roomCode() || (state.room && state.room.code);
  if (!code) return;
  $must("skip").disabled = true;
  try {
    /** @type {{ ok: boolean, data: Room }} */
    const { ok, data } = await fetchJson("/api/rooms/" + code + "/skip", { method: "POST" });
    if (!ok || !data.code) return;
    state.room = data;
    if (!state.room.now_playing) stopPlayback();
    else state.lastItem = "";
    if (state.room.now_playing) $must("title").textContent = state.room.now_playing.title;
    await tick();
  } finally {
    $must("skip").disabled = false;
  }
};
$must("toggle").onclick = async () => {
  const next = (state.room.vocal_mix || 0) > 0.5 ? 0 : 1;
  /** @type {{ data: Room }} */
  const { data } = await fetchJson("/api/rooms/" + (roomCode() || state.room.code) + "/mix", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vocal_mix: next }),
  });
  state.room = data;
  applyMix();
};
$must("karaoke").addEventListener("ended", () => $must("skip").click());

bootAuth().then(() => {
  bindRoomRtc(state.room.code);
  tick();
  setInterval(tick, 1500);
  requestAnimationFrame(paint);
});
