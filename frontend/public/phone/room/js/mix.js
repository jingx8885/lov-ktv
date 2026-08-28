import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";
import { showToast } from "../../ui/js/toast.js";
import { openOverlay } from "../../ui/js/overlays.js";

export function mixEditing() {
  return document.activeElement === $("hostVol") || document.activeElement === $("micGain");
}

export function paintVocalMix(mix) {
  const on = Number(mix) >= 0.5;
  $("vocalMix").classList.toggle("on", on);
  $("vocalMixLabel").textContent = on ? "原唱" : "伴奏";
  $("vocalMix").setAttribute("aria-label", on ? "当前原唱，点按切到伴奏" : "当前伴奏，点按切到原唱");
}

export function paintMix(room) {
  if (!room || mixEditing()) return;
  const vol = room.host_volume != null ? room.host_volume : (room.volume != null ? room.volume : 80);
  const gain = room.mic_gain != null ? room.mic_gain : 80;
  $("hostVol").value = String(vol);
  $("hostVolVal").textContent = String(vol);
  $("hostVolLabel").textContent = room.host_volume_kind === "mac" ? "Mac" : "音量";
  $("micGain").value = String(gain);
  $("micGainVal").textContent = String(gain);
  const live = !!(state.roomRtc && state.roomRtc.isLive());
  $("micToggle").classList.toggle("live", live);
  $("micToggle").classList.toggle("on", live || !!room.mic_on);
  $("micToggle").setAttribute("aria-label", live ? "关麦" : "开麦");
  $("micGainRow").hidden = !live;
  if (!live && !room.mic_on) {
    if (!$("micHint").dataset.hold) $("micHint").textContent = "";
  } else if (live) {
    $("micHint").textContent = room.mic_on ? "麦已接到电视" : "正在把麦接到电视…";
  }
}

export function postMix(body) {
  const code = $("room").value.trim().toUpperCase();
  if (!code) return;
  return fetch(`/api/rooms/${code}/mix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json()).then((room) => {
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
      return showToast("先填房间码并点进入");
    }
    $("skip").disabled = true;
    try {
      const room = await fetch(`/api/rooms/${code}/skip`, { method: "POST" }).then((r) => r.json());
      const now = room.now_playing;
      $("roomState").textContent = now
        ? `房间 ${room.code} · 正在唱 ${now.title}`
        : `房间 ${room.code} · 队列空`;
      api.showPage("desk", null, false);
      await api.loadRoom();
    } finally {
      $("skip").disabled = false;
    }
  };
}

api.paintVocalMix = paintVocalMix;
api.paintMix = paintMix;
