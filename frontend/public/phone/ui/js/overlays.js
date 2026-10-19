import { $, escapeHtml } from "../../../shared/ui/js/dom.js";

export function closeOverlay(id) {
  const el = $(id);
  if (el) el.hidden = true;
}

export function openOverlay(id) {
  const el = $(id);
  if (el) el.hidden = false;
}

/**
 * Confirm dialog (confirm/danger) or an action list.
 * items: [{ id, label, danger }] — resolves the chosen id; cancel/back resolve false.
 * @param {ActionSheetOpts} [opts]
 */
export function showActionSheet({ title, message, confirm, danger, items } = {}) {
  return new Promise((resolve) => {
    const root = $("actionSheet");
    $("actionSheetTitle").textContent = title || "";
    $("actionSheetTitle").hidden = !title;
    $("actionSheetMsg").textContent = message || "";
    $("actionSheetMsg").hidden = !message;
    const acts = $("actionSheetActs");
    if (Array.isArray(items) && items.length) {
      acts.innerHTML = items
        .map(
          (item) =>
            `<button type="button" class="action-btn ${item.danger ? "danger" : ""}" data-sheet-id="${escapeHtml(
              item.id
            )}">${escapeHtml(item.label)}</button>`
        )
        .join("");
    } else {
      acts.innerHTML = confirm
        ? `<button type="button" class="action-btn ${danger ? "danger" : ""}" id="actionSheetOk">${confirm}</button>`
        : "";
    }
    const finish = (value) => {
      root.hidden = true;
      resolve(value);
    };
    $("actionSheetCancel").onclick = () => finish(false);
    $("actionSheetBack").onclick = () => finish(false);
    acts.querySelectorAll("[data-sheet-id]").forEach((btn) => {
      btn.onclick = () => finish(btn.dataset.sheetId);
    });
    const ok = $("actionSheetOk");
    if (ok) ok.onclick = () => finish(true);
    root.hidden = false;
  });
}

export function bindOverlays() {
  document.querySelectorAll("[data-close-sheet]").forEach((btn) => {
    btn.onclick = () => {
      closeOverlay(btn.dataset.closeSheet);
      if (btn.dataset.closeSheet === "whoSheet") $("tabWho")?.classList.remove("on");
    };
  });
  $("topRoom").onclick = () => openOverlay("roomSheet");
  $("topWho").onclick = () => {
    $("tabWho")?.classList.add("on");
    openOverlay("whoSheet");
  };
  $("nowMore").onclick = () => openOverlay("mixSheet");
}
