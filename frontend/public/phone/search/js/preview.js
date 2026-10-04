import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { state } from "../../state.js";
import { ICO } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";

/** Sync every preview control (card badges and the sheet button) with
 *  ``state.previewId``. Called after playback starts or stops. */
export function repaintPreviewChrome() {
  document.querySelectorAll("[data-preview]").forEach((el) => {
    const playing = !!state.previewId && el.dataset.preview === String(state.previewId);
    el.classList.remove("busy");
    el.classList.toggle("on", playing);
    el.setAttribute("aria-label", playing ? t("phone.search.stopPreview") : t("phone.search.preview"));
    if (el.id === "hitSheetPlay") {
      el.innerHTML = playing
        ? `${ICO.pause}<span>${t("phone.search.stopPreview")}</span>`
        : `${ICO.play}<span>${t("phone.search.preview")}</span>`;
    } else {
      el.innerHTML = playing ? ICO.pause : ICO.play;
      el.closest(".hit-card")?.classList.toggle("is-playing", playing);
    }
  });
}

export function stopPreview() {
  for (const el of [$("preview"), $("hitVideo")]) {
    if (!el) continue;
    el.pause();
    el.removeAttribute("src");
    el.load();
    el.hidden = true;
  }
  state.previewId = "";
  repaintPreviewChrome();
}

export function previewParams(hit) {
  const params = new URLSearchParams({ title: hit.title || "", artist: hit.artist || "" });
  if (hit.media) params.set("media", hit.media);
  return params;
}

/** Toggle the preview for ``hit``; ``btn`` (the clicked control) shows a busy
 *  spinner while the resolve request is in flight. Pass null when the toggle
 *  is driven programmatically. */
export async function togglePreview(hit, btn) {
  if (state.previewId === String(hit.id)) {
    stopPreview();
    return;
  }
  stopPreview();
  if (btn) btn.classList.add("busy");
  const params = previewParams(hit);
  const { ok, data: info } = await fetchJson(`/api/preview/${encodeURIComponent(hit.id)}/resolve?` + params.toString());
  if (!ok) {
    if (btn) btn.classList.remove("busy");
    showToast(info.detail || t("phone.search.previewFail"));
    return;
  }
  state.previewId = String(hit.id);
  repaintPreviewChrome();
  // MV hits get the muxed video stream in the sheet; every other source
  // keeps the plain audio tag.  A dead video url falls back to audio once.
  const video = $("hitVideo");
  const audio = $("preview");
  const useVideo = !!(info && info.has_video) && video && sheetOpen();
  const el = useVideo ? video : audio;
  const videoParams = new URLSearchParams(params);
  if (useVideo) videoParams.set("format", "video");
  el.src = `/api/preview/${encodeURIComponent(hit.id)}?` + videoParams.toString();
  el.hidden = !useVideo;
  let retriedAudio = !useVideo;
  el.onerror = () => {
    if (state.previewId !== String(hit.id)) return;
    if (!retriedAudio) {
      retriedAudio = true;
      video.hidden = true;
      audio.src = `/api/preview/${encodeURIComponent(hit.id)}?` + params.toString();
      audio.play().catch(() => {
        stopPreview();
        showToast(t("phone.search.previewFail"));
      });
      return;
    }
    stopPreview();
    showToast(t("phone.search.previewFail"));
  };
  el.play().catch(() => {
    if (el.error) {
      el.onerror();
      return;
    }
    stopPreview();
    showToast(t("phone.search.previewFail"));
  });
  el.onended = stopPreview;
}

/** Whether the hit detail sheet is up and can host the video element. */
function sheetOpen() {
  const sheet = $("hitSheet");
  return !!sheet && !sheet.hidden;
}
