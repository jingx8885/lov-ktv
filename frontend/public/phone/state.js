import { guardState } from "../shared/ui/js/guard.js";
import { t } from "../shared/i18n/js/i18n.js";
import { catalogState } from "./catalog/state.js";
import { roomState } from "./room/state.js";
import { playerState } from "./player/state.js";

function ownSlice(target, slice) {
  Object.keys(slice).forEach((key) => {
    Object.defineProperty(target, key, {
      enumerable: true,
      configurable: false,
      get: () => slice[key],
      set: (value) => {
        slice[key] = value;
      }
    });
  });
}

/** @type {PhoneState} */
const phoneState = /** @type {PhoneState} */ ({ currentPage: "desk" });
ownSlice(phoneState, catalogState);
ownSlice(phoneState, roomState);
ownSlice(phoneState, playerState);

/** @type {PhoneState} */
export const state = guardState(phoneState, "phone");

export { catalogState, roomState, playerState };

export const STEP_MS = 100;
export const LIB_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ#".split("");
/** @type {string[]} */
export const PAGES = ["search", "desk", "player"];
/** @param {string} name */
export function pageTitle(name) {
  return t("phone.nav." + name);
}
export function searchEmpty() {
  return `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.search.empty")}</p><span class="tiny">${t("phone.search.emptyHint")}</span></div>`;
}
