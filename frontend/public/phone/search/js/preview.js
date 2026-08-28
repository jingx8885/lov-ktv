import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { state } from "../../state.js";
import { ICO } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";

export function stopPreview() {
  const audio = $("preview");
  audio.pause();
  audio.removeAttribute("src");
  state.previewId = "";
  $("hits").querySelectorAll("[data-preview]").forEach((btn) => {
    btn.classList.remove("on", "busy");
    btn.setAttribute("aria-label", "试听");
    btn.innerHTML = ICO.play;
  });
}

export function previewParams(hit) {
  const params = new URLSearchParams({ title: hit.title || "", artist: hit.artist || "" });
  if (hit.media) params.set("media", hit.media);
  return params;
}

export async function togglePreview(hit, btn) {
  if (state.previewId === hit.id) {
    stopPreview();
    return;
  }
  stopPreview();
  btn.classList.add("busy");
  const params = previewParams(hit);
  const { ok, data: info } = await fetchJson(`/api/preview/${encodeURIComponent(hit.id)}/resolve?` + params.toString());
  if (!ok) {
    btn.classList.remove("busy");
    showToast(info.detail || "这首暂时不能试听，换一条再听");
    return;
  }
  state.previewId = hit.id;
  btn.classList.add("on");
  btn.classList.remove("busy");
  btn.setAttribute("aria-label", "停止试听");
  btn.innerHTML = ICO.pause;
  const audio = $("preview");
  audio.src = `/api/preview/${encodeURIComponent(hit.id)}?` + params.toString();
  audio.play().catch(() => {
    stopPreview();
    showToast("这首暂时不能试听，换一条再听");
  });
  audio.onended = stopPreview;
}

