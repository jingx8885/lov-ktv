import { $ } from "../../../shared/ui/js/dom.js";

let hideTimer = 0;

export function showToast(message) {
  const el = $("toast");
  if (!el || !message) return;
  el.textContent = message;
  el.hidden = false;
  el.classList.add("on");
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    el.classList.remove("on");
    el.hidden = true;
  }, 2400);
}
