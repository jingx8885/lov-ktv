import "./install.js?v=paint3";
import { bootI18n, onLangChange, applyDom } from "../shared/i18n/js/i18n.js";
import { $must } from "../shared/ui/js/dom.js";
import { fetchJson } from "../shared/ui/js/http.js";
import { state } from "./state.js";
import { bootAuth, roomCode, renderUserChip } from "./auth/js/login.js";
import { unlockAudio } from "./audio/js/unlock.js";
import { bindRoomRtc } from "./audio/js/mic.js?v=paint3";
import { applyMix } from "./playback/js/mix.js?v=stall1";
import { tick, startPlayback, stopPlayback, pauseAudio, pageVisible, restoreResume, songReallyEnded, wantsResume } from "./playback/js/tick.js?v=paint3";
import { paint } from "./playback/js/lyrics.js?v=paint3";

bootI18n();
onLangChange(() => {
  applyDom();
  renderUserChip();
  applyMix();
});

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
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
    startPlayback();
  }
});
document.addEventListener("keydown", () => {
  unlockAudio();
  const karaoke = $must("karaoke");
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
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
$must("karaoke").addEventListener("ended", () => {
  const karaoke = $must("karaoke");
  if (songReallyEnded(karaoke)) {
    $must("skip").click();
    return;
  }
  restoreResume(karaoke);
  if (state.armed && state.room && state.room.now_playing) startPlayback();
});

bootAuth().then(() => {
  bindRoomRtc(state.room.code);
  tick();
  setInterval(tick, 1500);
  requestAnimationFrame(paint);
});
