import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { applyPlayerVocalMix, refreshPlayIcon, seekPlayerRatio, togglePlayer } from "./controls.js";
import { playNextSong, togglePlayOrder, updatePlayOrderBtns } from "./queue.js";

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
    state.playerClockHold = null;
    state.playerClockHoldAt = 0;
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
