import { $ } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { lanOrigin, roomUrl } from "../../../origin.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { applyLyricMode, lyricModeForScript, lyricScript } from "../../../../shared/lyrics/js/paint.js";
import { api } from "../../../api.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { closeOverlay } from "../../../ui/js/overlays.js";
import { nativeMicState, setNativeGain } from "../../../platform.js";

export function mixEditing() {
  return document.activeElement === $("hostVol") || document.activeElement === $("micGain");
}

export function paintVocalMix(mix) {
  const btn = $("vocalMix");
  const label = $("vocalMixLabel");
  const on = Number(mix) >= 0.5;
  if (btn) {
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-label", on ? t("phone.desk.vocalOn") : t("phone.desk.vocalOff"));
  }
  if (label) label.textContent = on ? t("common.vocal") : t("common.karaoke");
  const mixVocal = $("mixVocal");
  if (mixVocal) mixVocal.textContent = on ? t("common.vocal") : t("common.karaoke");
}

export function paintPaused(paused) {
  const on = !!paused;
  const btn = $("deskPause");
  const label = $("deskPauseLabel");
  if (btn) {
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-label", on ? t("common.play") : t("common.pause"));
  }
  if (label) label.textContent = on ? t("common.play") : t("common.pause");
}

export function paintDisplayMode(mode) {
  const on = String(mode || "mv").toLowerCase() !== "lyrics";
  document.body.classList.toggle("display-mv", on);
  document.body.classList.toggle("display-lyrics", !on);
  const btn = $("playerDisplayMode");
  const label = $("playerDisplayModeLabel");
  if (btn) {
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-label", on ? t("phone.player.mvMode") : t("phone.player.lyricsOnly"));
  }
  if (label) label.textContent = on ? t("phone.player.mvMode") : t("phone.player.lyricsOnly");
}

export { lyricModeForScript, lyricScript };

function lyricModeLabel(key, script) {
  if (key === "ja") {
    if (script === "en") return t("phone.lyric.en");
    return script === "ja" || !script ? t("phone.lyric.ja") : t("phone.lyric.src");
  }
  if (key === "zh") return t("phone.lyric.zh");
  if (key === "roma") return t("phone.lyric.roma");
  if (key === "all") return script === "zh" ? t("phone.lyric.lyrics") : t("phone.lyric.complete");
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
  [$("lyricModeSelect"), $("playerLyricModeSelect")].forEach((select) => {
    if (!select) return;
    [...select.options].forEach((option) => {
      const key = option.value || "";
      option.hidden = (script === "zh" && key !== "all") || (key === "roma" && !!script && script !== "ja");
      option.textContent = lyricModeLabel(key, script);
    });
    select.value = next;
    select.setAttribute("aria-label", t("phone.lyric.mode"));
  });
  if (api.paintDeskLyrics) api.paintDeskLyrics();
}

export function paintMix(room) {
  const hostVol = $("hostVol");
  const hostVolVal = $("hostVolVal");
  const hostVolLabel = $("hostVolLabel");
  const micGain = $("micGain");
  const micGainVal = $("micGainVal");
  if (!room || !hostVol || !hostVolVal || !hostVolLabel || !micGain || !micGainVal || mixEditing()) return;
  paintLyricMode(room.lyric_mode, room.now_playing && room.now_playing.language);
  paintDisplayMode(room.display_mode);
  paintPaused(!!room.paused);
  const vol = room.host_volume != null ? room.host_volume : room.volume != null ? room.volume : 80;
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
    body: JSON.stringify(body)
  })
    .then(({ data: room }) => {
      // paintMix intentionally leaves sliders alone while they are being
      // edited.  Lyric mode must still be applied from the authoritative
      // response so the phone and TV settle on the same selection.
      if (room && room.code) {
        paintLyricMode(room.lyric_mode, room.now_playing && room.now_playing.language);
        paintMix(room);
      }
      return room;
    })
    .catch(() => {});
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
  paintDisplayMode("mv");
  bindMixSlider("hostVol", "volume");
  bindMixSlider("micGain", "mic_gain");
  document.querySelectorAll("button[data-lyric-mode]").forEach((btn) => {
    btn.onclick = () => {
      paintLyricMode(btn.dataset.lyricMode);
      postMix({ lyric_mode: btn.dataset.lyricMode });
    };
  });
  const lyricSelect = $("lyricModeSelect");
  if (lyricSelect) {
    lyricSelect.onchange = () => {
      paintLyricMode(lyricSelect.value);
      postMix({ lyric_mode: lyricSelect.value });
    };
  }
  const playerLyricSelect = $("playerLyricModeSelect");
  if (playerLyricSelect) {
    playerLyricSelect.onchange = () => {
      paintLyricMode(playerLyricSelect.value);
      postMix({ lyric_mode: playerLyricSelect.value });
    };
  }
  const displayMode = $("playerDisplayMode");
  if (displayMode) {
    displayMode.onclick = () => {
      const next = displayMode.classList.contains("on") ? "lyrics" : "mv";
      paintDisplayMode(next);
      postMix({ display_mode: next });
    };
  }
  if ($("vocalMix"))
    $("vocalMix").onclick = () => {
      const next = $("vocalMix").classList.contains("on") ? 0 : 1;
      paintVocalMix(next);
      postMix({ vocal_mix: next });
    };
  if ($("mixVocal")) $("mixVocal").onclick = () => $("vocalMix") && $("vocalMix").click();
  if ($("mixSkip")) $("mixSkip").onclick = () => $("skip") && $("skip").click();
  if ($("deskPause"))
    $("deskPause").onclick = () => {
      if (api.needTvOrRoom && api.needTvOrRoom()) return;
      const next = !$("deskPause").classList.contains("on");
      paintPaused(next);
      postMix({ paused: next });
    };
  if ($("skip"))
    $("skip").onclick = async () => {
      const code = $("room").value.trim().toUpperCase();
      $("room").value = code;
      if (api.needTvOrRoom && api.needTvOrRoom()) return;
      $("skip").disabled = true;
      try {
        /** @type {{ ok: boolean, data: Room }} */
        const skipHit = await fetchJson(roomUrl(`/api/rooms/${code}/skip`), { method: "POST" });
        if (!skipHit.ok || !skipHit.data || !skipHit.data.code) {
          showToast(lanOrigin() ? t("phone.room.lanFail") : skipHit.data.detail || t("phone.desk.cantQueue"));
          return;
        }
        const room = skipHit.data;
        const now = room.now_playing;
        $("roomState").textContent = now
          ? t("phone.room.statNow", { code: room.code, title: now.title })
          : t("phone.room.statEmpty", { code: room.code });
        closeOverlay("mixSheet");
        api.showPage("desk", null, false);
        // The skip response already contains the fresh room snapshot; avoid
        // a second GET before repainting the queue and now-playing card.
        await api.loadRoom({ room });
      } finally {
        $("skip").disabled = false;
      }
    };
}
