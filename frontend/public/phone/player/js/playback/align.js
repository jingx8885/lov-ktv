import { $ } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { paintLine } from "../../../../shared/lyrics/js/paint.js";
import { api } from "../../../api.js";
import { state, STEP_MS } from "../../../state.js";
import { ICO } from "../../../ui/js/icons.js";
import { showToast } from "../../../ui/js/toast.js";
import { setPlayIcon, syncGuide, playFromMs, applyKaraokeGain } from "./controls.js";
import { cueIndexAt } from "./lyrics.js";
import { togglePlayOrder } from "./queue.js";

export function fmtMs(ms) {
  const n = Math.max(0, Math.floor(ms || 0));
  const m = Math.floor(n / 60000);
  const s = Math.floor((n % 60000) / 1000);
  const cs = Math.floor((n % 1000) / 10);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
}

export function syncEditAxis() {
  const rotated = document.body.classList.contains("edit-on") && window.matchMedia("(orientation: portrait)").matches;
  const tl = $("timeline");
  if (tl) tl.dataset.axis = rotated ? "y" : "x";
}

export function applyEditorTracks() {
  const editing = document.body.classList.contains("edit-on");
  $("playerAudio").muted = editing && !state.mixTrackOn;
  $("tlMixHead").classList.toggle("off", !state.mixTrackOn);
  $("tlMixHead").setAttribute("aria-pressed", state.mixTrackOn ? "true" : "false");
  $("tlVoiceHead").classList.toggle("off", !state.voiceTrackOn);
  $("tlVoiceHead").setAttribute("aria-pressed", state.voiceTrackOn ? "true" : "false");
  $("timeline").classList.toggle("mix-off", !state.mixTrackOn);
  $("timeline").classList.toggle("voice-off", !state.voiceTrackOn);
  if (state.alignTl) {
    state.alignTl.setMixOn(state.mixTrackOn);
    state.alignTl.setVoiceOn(state.voiceTrackOn);
  }
  applyKaraokeGain();
}

export function exitEdit() {
  document.body.classList.remove("edit-on");
  $("playerAlign").hidden = true;
  $("playerAudio").muted = false;
  try {
    screen.orientation.unlock();
  } catch (err) {}
  syncEditAxis();
  syncGuide();
}

export function enterEdit() {
  if (!state.playerSong) return showToast(t("phone.player.needSong"));
  $("playerAlign").hidden = false;
  document.body.classList.add("edit-on");
  state.mixTrackOn = false;
  state.voiceTrackOn = true;
  applyEditorTracks();
  syncEditAxis();
  try {
    screen.orientation.lock("landscape");
  } catch (err) {}
  setPlayIcon(!$("playerAudio").paused);
  syncGuide();
  requestAnimationFrame(() => {
    ensureTimeline().render();
    applyEditorTracks();
  });
}

export function ensureTimeline() {
  if (state.alignTl) return state.alignTl;
  state.alignTl = LovTimeline.create({
    root: $("timeline"),
    stage: $("tlStage"),
    wave: $("tlWave"),
    voice: $("tlVoiceWave"),
    ruler: $("tlRuler"),
    track: $("tlTrack"),
    getCues: () => state.playerLyrics.cues || [],
    getAudio: () => $("playerAudio"),
    selected: () => state.selectedCue,
    onSeek: (ms) => syncGuide(ms / 1000),
    onSelect: (index) => {
      state.selectedCue = index;
      updateAlignNow();
    },
    onGrab: () => {
      $("playerAudio").pause();
      setPlayIcon(false);
      syncGuide();
    },
    onReleaseCue: (cue) => playFromMs(cue.start_ms),
    onChange: () => {
      state.lyricsDirty = true;
      updateAlignNow();
    }
  });
  return state.alignTl;
}

export function updateAlignNow(playMs) {
  const cues = state.playerLyrics.cues || [];
  const dragging = !!(state.alignTl && state.alignTl.isDragging());
  let index = state.selectedCue;
  if (playMs != null && !dragging) index = cueIndexAt(playMs);
  const cue = cues[index];
  if (!cue) {
    $("alignTime").textContent = playMs != null ? fmtMs(playMs) : "";
    if (state.lyricPaint.align !== "hint") {
      $("alignText").textContent = t("phone.align.hint");
      state.lyricPaint.align = "hint";
    }
    return;
  }
  const clock = playMs != null && !dragging ? fmtMs(playMs) : fmtMs(cue.start_ms);
  if ($("alignTime").textContent !== clock) $("alignTime").textContent = clock;
  paintLine($("alignText"), cue, playMs != null && !dragging ? playMs : -1, "align", state.lyricPaint);
}

export function renderAlignList() {
  updateAlignNow();
  ensureTimeline().render();
}

function syncRegenerateVisibility() {
  const btn = $("playerRegenerate");
  if (btn) btn.hidden = !state.songAdmin || !state.playerSong;
}

async function regenerateLyrics() {
  const song = state.playerSong;
  if (!song) return showToast(t("phone.player.needSong"));
  const btn = $("playerRegenerate");
  if (btn.disabled) return;
  btn.disabled = true;
  try {
    const started = await fetchJson(`/api/songs/${song.id}/realign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rebuild_mtv: false, force: true })
    });
    if (!started.ok) throw new Error(started.data?.detail || t("phone.player.regenerateFailed"));
    showToast(t("phone.player.regenerateStarted"));
    for (let attempt = 0; attempt < 360; attempt += 1) {
      await new Promise((resolve) => {
        setTimeout(resolve, 1500);
      });
      const current = await fetchJson(`/api/songs/${song.id}`, { cache: "no-store" }).catch(() => null);
      const status = current && current.data && current.data.status;
      if (status === "failed") throw new Error(t("phone.player.regenerateFailed"));
      if (status !== "ready") continue;
      const { loadPlayerSong } = await import("./song.js");
      await loadPlayerSong(song.id, { play: false });
      showToast(t("phone.player.regenerateDone"));
      return;
    }
    throw new Error(t("phone.player.regenerateFailed"));
  } catch (err) {
    showToast(err instanceof Error ? err.message : t("phone.player.regenerateFailed"));
  } finally {
    btn.disabled = false;
  }
}

export function shiftSelected(delta, rest) {
  const cues = state.playerLyrics.cues || [];
  if (state.selectedCue < 0 || state.selectedCue >= cues.length) return;
  const last = rest ? cues.length : state.selectedCue + 1;
  for (let i = state.selectedCue; i < last; i += 1) {
    cues[i].start_ms += delta;
    cues[i].end_ms += delta;
    (cues[i].tokens || []).forEach((tok) => {
      tok.start_ms += delta;
      tok.end_ms += delta;
    });
  }
  for (let i = 0; i < cues.length; i += 1) {
    const prevEnd = i ? cues[i - 1].end_ms : 0;
    const nxt = i + 1 < cues.length ? cues[i + 1].start_ms : null;
    let start = Math.max(0, prevEnd, cues[i].start_ms);
    let end = Math.max(start + 200, cues[i].end_ms);
    if (nxt != null && end > nxt) {
      end = nxt;
      if (end < start + 200) {
        start = Math.max(prevEnd, nxt - 200);
        end = nxt;
      }
    }
    cues[i].start_ms = start;
    cues[i].end_ms = end;
  }
  state.lyricsDirty = true;
  renderAlignList();
}

export function bindAlign() {
  $("editPlay").onclick = () => api.togglePlayer();
  $("playerEdit").onclick = () => enterEdit();
  $("playerRegenerate").onclick = () => regenerateLyrics();
  syncRegenerateVisibility();
  document.addEventListener("lovktv-auth-change", syncRegenerateVisibility);
  $("editBack").onclick = () => exitEdit();
  $("tlMixHead").onclick = () => {
    state.mixTrackOn = !state.mixTrackOn;
    applyEditorTracks();
  };
  $("tlVoiceHead").onclick = () => {
    state.voiceTrackOn = !state.voiceTrackOn;
    applyEditorTracks();
    syncGuide();
  };
  $("nudgeBack").onclick = () => {
    shiftSelected(-STEP_MS, state.chainRest);
    ensureTimeline().render();
  };
  $("nudgeFwd").onclick = () => {
    shiftSelected(STEP_MS, state.chainRest);
    ensureTimeline().render();
  };
  $("tlZoomOut").onclick = () => ensureTimeline().zoom(-1);
  $("tlZoomIn").onclick = () => ensureTimeline().zoom(1);
  $("tlChain").onclick = () => {
    state.chainRest = !state.chainRest;
    $("tlChain").textContent = state.chainRest ? t("phone.align.chainRest") : t("phone.align.chain");
    $("tlChain").classList.toggle("primary", state.chainRest);
    ensureTimeline().setChain(state.chainRest);
  };
  $("saveAlign").onclick = async () => {
    if (!state.playerSong || !(state.playerLyrics.cues || []).length) return;
    const btn = $("saveAlign");
    btn.disabled = true;
    try {
      const { ok, data } = await fetchJson(`/api/songs/${state.playerSong.id}/lyrics`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state.playerLyrics)
      });
      if (!ok) throw new Error(data.detail || t("common.saveFailed"));
      state.lyricsDirty = false;
      btn.classList.add("on");
      btn.setAttribute("aria-label", t("common.saved"));
      btn.innerHTML = ICO.save;
      setTimeout(() => {
        btn.classList.remove("on");
        btn.setAttribute("aria-label", t("common.save"));
      }, 1200);
    } catch (err) {
      btn.setAttribute("aria-label", t("common.saveFailed"));
      setTimeout(() => btn.setAttribute("aria-label", t("common.save")), 1600);
    } finally {
      btn.disabled = false;
    }
  };
  $("playerOrderEdit").onclick = () => togglePlayOrder();
  $("playerNextEdit").onclick = () => api.playNextSong();
  window.addEventListener("orientationchange", () => {
    syncEditAxis();
    if (document.body.classList.contains("edit-on")) requestAnimationFrame(() => ensureTimeline().render());
  });
  window.addEventListener("resize", () => {
    if (!document.body.classList.contains("edit-on")) return;
    syncEditAxis();
    ensureTimeline().render();
  });
}
