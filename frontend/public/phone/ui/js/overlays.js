import { $ } from "../../../shared/ui/js/dom.js";

export function closeOverlay(id) {
  const el = $(id);
  if (el) el.hidden = true;
}

export function openOverlay(id) {
  const el = $(id);
  if (el) el.hidden = false;
}

/** @param {ActionSheetOpts} [opts] */
export function showActionSheet({ title, message, confirm, danger } = {}) {
  return new Promise((resolve) => {
    const root = $("actionSheet");
    $("actionSheetTitle").textContent = title || "";
    $("actionSheetTitle").hidden = !title;
    $("actionSheetMsg").textContent = message || "";
    $("actionSheetMsg").hidden = !message;
    $("actionSheetActs").innerHTML = confirm
      ? `<button type="button" class="action-btn ${danger ? "danger" : ""}" id="actionSheetOk">${confirm}</button>`
      : "";
    const finish = (value) => {
      root.hidden = true;
      resolve(value);
    };
    $("actionSheetCancel").onclick = () => finish(false);
    $("actionSheetBack").onclick = () => finish(false);
    const ok = $("actionSheetOk");
    if (ok) ok.onclick = () => finish(true);
    root.hidden = false;
  });
}

export function bindOverlays() {
  document.querySelectorAll("[data-close-sheet]").forEach((btn) => {
    btn.onclick = () => closeOverlay(btn.dataset.closeSheet);
  });
  $("topRoom").onclick = () => openOverlay("roomSheet");
  $("topWho").onclick = () => openOverlay("whoSheet");
  $("nowMore").onclick = () => openOverlay("mixSheet");
}
