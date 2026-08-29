import "./install.js";
import { bootI18n, onLangChange, applyDom } from "../shared/i18n/js/i18n.js";
import { $must } from "../shared/ui/js/dom.js";
import { state } from "./state.js";
import { bootAuth, renderUserChip } from "./auth/js/login.js";
import { unlockAudio } from "./audio/js/unlock.js";
import { bindRoomRtc } from "./audio/js/mic.js";
import { applyMix } from "./playback/js/mix.js";
import { tick, startPlayback, pauseAudio, pageVisible, restoreResume, songReallyEnded, wantsResume } from "./playback/js/tick.js";
import { paint } from "./playback/js/lyrics.js";
import { bindRemote, skipSong, toggleVocal, paintSettings } from "./playback/js/remote.js";

bootI18n();
onLangChange(() => {
  applyDom();
  renderUserChip();
  applyMix();
  paintSettings();
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
  if (state.room && state.room.paused) return;
  if (state.armed && state.room && state.room.now_playing) startPlayback();
});

$must("start").onclick = () => {
  unlockAudio();
  startPlayback();
};
document.addEventListener("pointerdown", () => {
  unlockAudio();
  if (state.room && state.room.paused) return;
  const karaoke = $must("karaoke");
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
    startPlayback();
  }
});
document.addEventListener("keydown", () => {
  unlockAudio();
  if (state.room && state.room.paused) return;
  const karaoke = $must("karaoke");
  if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
    startPlayback();
  }
});
$must("skip").onclick = () => skipSong();
$must("toggle").onclick = () => toggleVocal();
$must("karaoke").addEventListener("ended", () => {
  const karaoke = $must("karaoke");
  if (songReallyEnded(karaoke)) {
    skipSong();
    return;
  }
  restoreResume(karaoke);
  if (state.armed && state.room && state.room.now_playing) startPlayback();
});
bindRemote();

bootAuth().then(() => {
  bindRoomRtc(state.room.code);
  tick();
  setInterval(tick, 1500);
  requestAnimationFrame(paint);
}).catch((err) => {
  const qr = document.getElementById("qr");
  if (qr && qr.querySelector("canvas, img, svg")) return;
  const code = document.getElementById("code");
  if (code) code.textContent = "开房失败";
  if (qr) qr.textContent = (err && err.message) || "请按菜单键检查处理服务器";
});
