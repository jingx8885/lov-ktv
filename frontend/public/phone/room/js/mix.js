import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { lanOrigin, roomUrl } from "../../origin.js?v=scan1";
import { t } from "../../../shared/i18n/js/i18n.js";
import { applyLyricMode, lyricModeForScript, lyricScript } from "../../../shared/lyrics/js/paint.js?v=paint3";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { closeOverlay } from "../../ui/js/overlays.js";
import { nativeMicState, setNativeGain } from "./native-mic.js?v=micudp1";

export function mixEditing() {
  return document.activeElement === $("hostVol") || document.activeElement === $("micGain");
}

export function paintVocalMix(mix) {
  const btn = $("vocalMix");
  const label = $("vocalMixLabel");
  if (!btn || !label) return;
  const on = Number(mix) >= 0.5;
  btn.classList.toggle("on", on);
  label.textContent = on ? t("common.vocal") : t("common.karaoke");
  btn.setAttribute("aria-label", on ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff"));
}

export { lyricModeForScript, lyricScript };

function lyricModeLabel(key, script) {
  if (key === "ja") return script === "ja" || !script ? t("phone.lyric.ja") : t("phone.lyric.src");
  if (key === "zh") return t("phone.lyric.zh");
  if (key === "roma") return t("phone.lyric.roma");
  if (key === "all") return t("phone.lyric.all");
  return "";
}

export function paintLyricMode(mode, language) {
  if (language != null) state.nowLanguage = String(language || "");
  const script = lyricScript(state.nowLanguage);
  const next = lyricModeForScript(mode, script);
  state.lyricMode = next;
  applyLyricMode(document.body, next, state.nowLanguage);
  document.querySelectorAll(".lyric-seg").forEach((seg) => {
    seg.dataset.lyricScript = script;
  });
  document.querySelectorAll("button[data-lyric-mode]").forEach((btn) => {
    const key = btn.dataset.lyricMode || "";
    btn.hidden = key === "roma" && !!script && script !== "ja";
    btn.classList.toggle("on", key === next);
    btn.textContent = lyricModeLabel(key, script);
  });
}

export function paintMix(room) {
  const hostVol = $("hostVol");
  const hostVolVal = $("hostVolVal");
  const hostVolLabel = $("hostVolLabel");
  const micGain = $("micGain");
  const micGainVal = $("micGainVal");
  if (!room || !hostVol || !hostVolVal || !hostVolLabel || !micGain || !micGainVal || mixEditing()) return;
  paintLyricMode(room.lyric_mode, room.now_playing && room.now_playing.language);
  const vol = room.host_volume != null ? room.host_volume : (room.volume != null ? room.volume : 80);
  const gain = room.mic_gain != null ? room.mic_gain : 80;
  hostVol.value = String(vol);
  hostVolVal.textContent = String(vol);
  hostVolLabel.textContent = room.host_volume_kind === "mac" ? "Mac" : t("common.volume");
  micGain.value = String(gain);
  micGainVal.textContent = String(gain);
  const live = !!(nativeMicState().tv || (state.roomRtc && state.roomRtc.isLive()));
  const micToggle = $("micToggle");
  if (micToggle) {
    micToggle.classList.toggle("live", live);
    micToggle.classList.toggle("on", live || !!room.mic_on);
    micToggle.setAttribute("aria-label", live ? t("common.micOff") : t("common.micOn"));
  }
  if ($("micToggleLabel")) $("micToggleLabel").textContent = live ? t("common.micOff") : t("common.micOn");
  if ($("micGainRow")) $("micGainRow").hidden = !live;
  const micHint = $("micHint");
  if (!micHint) return;
  if (!live && !room.mic_on) {
    if (!micHint.dataset.hold) micHint.textContent = "";
  } else if (live) {
    micHint.textContent = nativeMicState().tv || room.mic_on ? t("phone.mic.liveTv") : t("phone.mic.linking");
  }
}

export function postMix(body) {
  const roomEl = $("room");
  const code = roomEl ? roomEl.value.trim().toUpperCase() : "";
  if (!code) return;
  return fetchJson(roomUrl(`/api/rooms/${code}/mix`), {
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
  if (!el) return;
  const slide = () => {
    $(id === "hostVol" ? "hostVolVal" : "micGainVal").textContent = el.value;
    if (id === "micGain") setNativeGain(el.value);
    clearTimeout(state.mixTimer);
    state.mixTimer = setTimeout(() => postMix({ [key]: Number(el.value) }), 80);
  };
  el.addEventListener("input", slide);
  el.addEventListener("change", () => postMix({ [key]: Number(el.value) }));
}

export function bindMix() {
  bindMixSlider("hostVol", "volume");
  bindMixSlider("micGain", "mic_gain");
  document.querySelectorAll("button[data-lyric-mode]").forEach((btn) => {
    btn.onclick = () => {
      paintLyricMode(btn.dataset.lyricMode);
      postMix({ lyric_mode: btn.dataset.lyricMode });
    };
  });
  if ($("vocalMix")) $("vocalMix").onclick = () => {
    const next = $("vocalMix").classList.contains("on") ? 0 : 1;
    paintVocalMix(next);
    fetch(roomUrl(`/api/rooms/${$("room").value}/mix`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vocal_mix: next }),
    });
  };
  if ($("skip")) $("skip").onclick = async () => {
    const code = $("room").value.trim().toUpperCase();
    $("room").value = code;
    if (api.needTvOrRoom && api.needTvOrRoom()) return;
    $("skip").disabled = true;
    try {
      /** @type {{ data: Room }} */
      const skipHit = await fetchJson(roomUrl(`/api/rooms/${code}/skip`), { method: "POST" });
      if (!skipHit.ok || !skipHit.data || !skipHit.data.code) {
        showToast(lanOrigin() ? t("phone.room.lanFail") : (skipHit.data.detail || t("phone.desk.cantQueue")));
        return;
      }
      const room = skipHit.data;
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

