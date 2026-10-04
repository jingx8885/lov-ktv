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
  const audio = $("preview");
  audio.pause();
  audio.removeAttribute("src");
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
  const audio = $("preview");
  audio.src = `/api/preview/${encodeURIComponent(hit.id)}?` + params.toString();
  audio.play().catch(() => {
    stopPreview();
    showToast(t("phone.search.previewFail"));
  });
  audio.onended = stopPreview;
}
