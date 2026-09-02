import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import {
  applyPlayerVocalMix,
  kickPlayerPaint,
  refreshPlayIcon,
  seekPlayerRatio,
  switchPlayerTrack,
  togglePlayer
} from "./controls.js";
import { playNextSong, togglePlayOrder, updatePlayOrderBtns } from "./queue.js";

export function bindPlayback() {
  $("playerPlay").onclick = () => togglePlayer();
  const playerArt = $("playerArt");
  if (playerArt) {
    playerArt.addEventListener("click", (event) => {
      // 画面上的全屏按钮等控件保留各自行为，不冒泡成播放切换。
      if (event.target instanceof Element && event.target.closest("button, input, select, label, a")) return;
      togglePlayer();
    });
  }
  ["play", "playing", "pause", "ended", "seeking", "timeupdate"].forEach((name) => {
    $("playerAudio").addEventListener(name, refreshPlayIcon);
  });
  // 切歌后元数据和时间轴是异步到达的，主动唤醒绘制，避免沿用旧歌的进度/歌词画面。
  ["loadedmetadata", "durationchange", "timeupdate", "progress", "canplay"].forEach((name) => {
    $("playerAudio").addEventListener(name, kickPlayerPaint);
  });
  $("playerVocal").onclick = () => {
    state.playerVocal = state.playerVocal ? 0 : 1;
    localStorage.setItem("playerVocal", state.playerVocal ? "1" : "0");
    $("playerVocal").classList.toggle("on", !!state.playerVocal);
    $("playerVocalLabel").textContent = state.playerVocal ? t("common.vocal") : t("common.karaoke");
    $("playerVocal").setAttribute("aria-label", state.playerVocal ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff"));
    state.playerClockHold = null;
    state.playerClockHoldAt = 0;
    switchPlayerTrack(state.playerVocal).then(() => applyPlayerVocalMix());
  };
  ["playerSeek", "playerSeekDock"].forEach((id) => {
    const seek = $(id);
    if (!seek) return;
    seek.addEventListener("input", () => {
      const ratio = Number(seek.value) / 1000;
      ["playerSeek", "playerSeekDock"].forEach((otherId) => {
        const other = $(otherId);
        if (other && other !== seek) other.value = seek.value;
        if (other) other.style.setProperty("--seek-p", `${ratio * 100}%`);
      });
      seekPlayerRatio(ratio);
    });
  });
  $("playerAudio").onended = () => {
    if (document.body.classList.contains("learn-on")) return;
    if (state.playerClockHold != null) return;
    const audio = $("playerAudio");
    const dur = audio.duration;
    const current = audio.currentTime || 0;
    if (!Number.isFinite(dur) || dur < 0.5) return;
    if (current < dur * 0.95 && current < dur - 0.35) return;
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
