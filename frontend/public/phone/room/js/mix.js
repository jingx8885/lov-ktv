import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { applyLyricMode, normLyricMode } from "../../../shared/lyrics/js/paint.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { closeOverlay, openOverlay } from "../../ui/js/overlays.js";

export function mixEditing() {
  return document.activeElement === $("hostVol") || document.activeElement === $("micGain");
}

export function paintVocalMix(mix) {
  const on = Number(mix) >= 0.5;
  $("vocalMix").classList.toggle("on", on);
  $("vocalMixLabel").textContent = on ? t("common.vocal") : t("common.karaoke");
  $("vocalMix").setAttribute("aria-label", on ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff"));
}

export function paintLyricMode(mode, language) {
  const next = normLyricMode(mode);
  state.lyricMode = next;
  if (language != null) state.nowLanguage = String(language || "");
  applyLyricMode(document.body, next);
  const jaLabel = state.nowLanguage === "ja" ? t("phone.lyric.ja") : t("phone.lyric.src");
  document.querySelectorAll("[data-lyric-mode]").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.lyricMode === next);
    if (btn.dataset.lyricMode === "ja") btn.textContent = jaLabel;
  });
}

export function paintMix(room) {
  if (!room || mixEditing()) return;
  paintLyricMode(room.lyric_mode, room.now_playing && room.now_playing.language);
  const vol = room.host_volume != null ? room.host_volume : (room.volume != null ? room.volume : 80);
  const gain = room.mic_gain != null ? room.mic_gain : 80;
  $("hostVol").value = String(vol);
  $("hostVolVal").textContent = String(vol);
  $("hostVolLabel").textContent = room.host_volume_kind === "mac" ? "Mac" : t("common.volume");
  $("micGain").value = String(gain);
  $("micGainVal").textContent = String(gain);
  const live = !!(state.roomRtc && state.roomRtc.isLive());
  $("micToggle").classList.toggle("live", live);
  $("micToggle").classList.toggle("on", live || !!room.mic_on);
  $("micToggle").setAttribute("aria-label", live ? t("common.micOff") : t("common.micOn"));
  if ($("micToggleLabel")) $("micToggleLabel").textContent = live ? t("common.micOff") : t("common.micOn");
  $("micGainRow").hidden = !live;
  if (!live && !room.mic_on) {
    if (!$("micHint").dataset.hold) $("micHint").textContent = "";
  } else if (live) {
    $("micHint").textContent = room.mic_on ? t("phone.mic.liveTv") : t("phone.mic.linking");
  }
}

export function postMix(body) {
  const code = $("room").value.trim().toUpperCase();
  if (!code) return;
  return fetchJson(`/api/rooms/${code}/mix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(({ data: room }) => {
    paintMix(room);
    return room;
  }).catch(() => {});
}

export function bindMixSlider(id, key) {
  const el = $(id);
  const slide = () => {
    $(id === "hostVol" ? "hostVolVal" : "micGainVal").textContent = el.value;
    clearTimeout(state.mixTimer);
    state.mixTimer = setTimeout(() => postMix({ [key]: Number(el.value) }), 80);
  };
  el.addEventListener("input", slide);
  el.addEventListener("change", () => postMix({ [key]: Number(el.value) }));
}

export function bindMix() {
  bindMixSlider("hostVol", "volume");
  bindMixSlider("micGain", "mic_gain");
  document.querySelectorAll("[data-lyric-mode]").forEach((btn) => {
    btn.onclick = () => {
      paintLyricMode(btn.dataset.lyricMode);
      postMix({ lyric_mode: btn.dataset.lyricMode });
    };
  });
  $("vocalMix").onclick = () => {
    const next = $("vocalMix").classList.contains("on") ? 0 : 1;
    paintVocalMix(next);
    fetch(`/api/rooms/${$("room").value}/mix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vocal_mix: next }),
    });
  };
  $("skip").onclick = async () => {
    const code = $("room").value.trim().toUpperCase();
    $("room").value = code;
    if (!code) {
      openOverlay("roomSheet");
      return showToast(t("phone.desk.needRoom"));
    }
    $("skip").disabled = true;
    try {
      /** @type {{ data: Room }} */
      const { data: room } = await fetchJson(`/api/rooms/${code}/skip`, { method: "POST" });
      const now = room.now_playing;
      $("roomState").textContent = now
        ? t("phone.room.statNow", { code: room.code, title: now.title })
        : t("phone.room.statEmpty", { code: room.code });
      closeOverlay("mixSheet");
      api.showPage("desk", null, false);
      await api.loadRoom();
    } finally {
      $("skip").disabled = false;
    }
  };
}

