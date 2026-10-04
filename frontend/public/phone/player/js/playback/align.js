import { $ } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { paintLine } from "../../../../shared/lyrics/js/paint.js";
import { api } from "../../../api.js";
import { state, STEP_MS } from "../../../state.js";
import { ICO } from "../../../ui/js/icons.js";
import { showToast } from "../../../ui/js/toast.js";
import { showActionSheet } from "../../../ui/js/overlays.js";
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

// Undo snapshots keep timing only; lyrics text/tokens stay untouched.
const ALIGN_HISTORY_MAX = 80;
let alignHistory = [];

function cueSnapshot() {
  return (state.playerLyrics.cues || []).map((cue) => ({
    start_ms: cue.start_ms,
    end_ms: cue.end_ms,
    tokens: (cue.tokens || []).map((tok) => [tok.start_ms, tok.end_ms])
  }));
}

function restoreSnapshot(snap) {
  const cues = state.playerLyrics.cues || [];
  if (!snap || snap.length !== cues.length) return false;
  for (let i = 0; i < cues.length; i += 1) {
    cues[i].start_ms = snap[i].start_ms;
    cues[i].end_ms = snap[i].end_ms;
    const toks = cues[i].tokens || [];
    for (let j = 0; j < toks.length && j < snap[i].tokens.length; j += 1) {
      toks[j].start_ms = snap[i].tokens[j][0];
      toks[j].end_ms = snap[i].tokens[j][1];
    }
  }
  return true;
}

function pushAlignHistory() {
  alignHistory.push(cueSnapshot());
  if (alignHistory.length > ALIGN_HISTORY_MAX) alignHistory.shift();
  syncUndoBtn();
}

function syncUndoBtn() {
  const btn = $("undoAlign");
  if (btn) btn.disabled = !alignHistory.length;
}

export function syncSaveDirty() {
  const btn = $("saveAlign");
  if (!btn) return;
  const dirty = !!state.lyricsDirty;
  btn.classList.toggle("dirty", dirty);
  btn.setAttribute("aria-label", dirty ? `${t("common.save")}（${t("phone.align.unsaved")}）` : t("common.save"));
}

function markDirty() {
  state.lyricsDirty = true;
  syncSaveDirty();
}

function undoAlign() {
  const snap = alignHistory.pop();
  syncUndoBtn();
  if (!restoreSnapshot(snap)) return;
  markDirty();
  updateAlignNow();
  ensureTimeline().render();
}

function repairCues() {
  const cues = state.playerLyrics.cues || [];
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
}

function shiftCues(from, delta, rest) {
  const cues = state.playerLyrics.cues || [];
  const last = rest ? cues.length : from + 1;
  for (let i = from; i < last; i += 1) {
    cues[i].start_ms += delta;
    cues[i].end_ms += delta;
    (cues[i].tokens || []).forEach((tok) => {
      tok.start_ms += delta;
      tok.end_ms += delta;
    });
  }
  repairCues();
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
  alignHistory = [];
  syncUndoBtn();
  syncSaveDirty();
  const cues = state.playerLyrics.cues || [];
  if (cues.length) {
    const at = cueIndexAt(($("playerAudio").currentTime || 0) * 1000);
    state.selectedCue = Math.min(Math.max(at, 0), cues.length - 1);
  }
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
    onFirstMove: () => pushAlignHistory(),
    onReleaseCue: (cue) => playFromMs(cue.start_ms),
    onChange: () => {
      markDirty();
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
  pushAlignHistory();
  shiftCues(state.selectedCue, delta, rest);
  markDirty();
  renderAlignList();
}

export function gotoCue(delta) {
  const cues = state.playerLyrics.cues || [];
  if (!cues.length) return;
  let index = state.selectedCue;
  if (index < 0 || index >= cues.length) {
    index = cueIndexAt(($("playerAudio").currentTime || 0) * 1000);
  }
  index = Math.min(cues.length - 1, Math.max(0, (index >= 0 ? index : 0) + delta));
  state.selectedCue = index;
  ensureTimeline().seek(cues[index].start_ms);
  updateAlignNow();
  ensureTimeline().render();
}

// Snap the current line's start to the playhead: the classic tap-along fix.
export function markAtPlayhead() {
  const cues = state.playerLyrics.cues || [];
  if (!cues.length) return;
  const audio = $("playerAudio");
  const playMs = (audio.currentTime || 0) * 1000;
  let index = state.selectedCue;
  if (index < 0 || index >= cues.length) index = cueIndexAt(playMs);
  if (index < 0 || index >= cues.length) index = cues.length - 1;
  const cue = cues[index];
  if (Math.abs(playMs - cue.start_ms) < 30) return;
  state.selectedCue = index;
  pushAlignHistory();
  shiftCues(index, playMs - cue.start_ms, state.chainRest);
  markDirty();
  updateAlignNow();
  ensureTimeline().render();
}

export async function editSong(songId) {
  if (!songId) return;
  if (!(state.playerSong && String(state.playerSong.id) === String(songId))) {
    await api.loadPlayerSong(songId, { play: false });
    if (!(state.playerSong && String(state.playerSong.id) === String(songId))) {
      showToast(t("phone.player.notReady"));
      return;
    }
  }
  api.showPage("player");
  enterEdit();
}

async function exitEditChecked() {
  if (state.lyricsDirty) {
    const drop = await showActionSheet({
      title: t("phone.align.unsavedTitle"),
      message: t("phone.align.unsavedMsg"),
      confirm: t("phone.align.discard"),
      danger: true
    });
    if (!drop) return;
    state.lyricsDirty = false;
    syncSaveDirty();
  }
  exitEdit();
}

export function bindAlign() {
  $("editPlay").onclick = () => api.togglePlayer();
  $("playerEdit").onclick = () => enterEdit();
  const editChip = $("playerEditChip");
  if (editChip) editChip.onclick = () => enterEdit();
  syncEditEntry();
  document.addEventListener("lovktv-auth-change", syncEditEntry);
  $("playerRegenerate").onclick = () => regenerateLyrics();
  syncRegenerateVisibility();
  document.addEventListener("lovktv-auth-change", syncRegenerateVisibility);
  $("editBack").onclick = () => exitEditChecked();
  $("cuePrev").onclick = () => gotoCue(-1);
  $("cueNext").onclick = () => gotoCue(1);
  $("markPlayhead").onclick = () => markAtPlayhead();
  $("undoAlign").onclick = () => undoAlign();
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
      alignHistory = [];
      syncUndoBtn();
      syncSaveDirty();
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
  window.addEventListener("beforeunload", (event) => {
    if (state.lyricsDirty && document.body.classList.contains("edit-on")) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  document.addEventListener("keydown", (event) => {
    if (!document.body.classList.contains("edit-on")) return;
    const target = /** @type {HTMLElement | null} */ (event.target);
    const tag = (target && target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (event.key === " " || event.code === "Space") {
      event.preventDefault();
      api.togglePlayer();
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const step = event.shiftKey ? 1000 : STEP_MS;
      shiftSelected(event.key === "ArrowRight" ? step : -step, state.chainRest);
      ensureTimeline().render();
    } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      gotoCue(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "m" || event.key === "M") {
      event.preventDefault();
      markAtPlayhead();
    } else if ((event.metaKey || event.ctrlKey) && (event.key === "z" || event.key === "Z")) {
      event.preventDefault();
      undoAlign();
    }
  });
}

export function syncEditEntry() {
  const show = !!state.playerSong;
  const chip = $("playerEditChip");
  if (chip) chip.hidden = !show;
  const icon = $("playerEdit");
  if (icon) icon.hidden = !show;
}
