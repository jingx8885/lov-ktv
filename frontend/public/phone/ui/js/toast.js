import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";

export function showToast(message) {
  const el = $("toast");
  if (!el || !message) return;
  el.textContent = message;
  el.hidden = false;
  el.classList.add("on");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    el.classList.remove("on");
    el.hidden = true;
  }, 2400);
}

api.showToast = showToast;
