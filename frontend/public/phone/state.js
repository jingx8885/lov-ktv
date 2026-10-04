import { guardState } from "../shared/ui/js/guard.js";
import { t } from "../shared/i18n/js/i18n.js";
import { escapeHtml } from "../shared/ui/js/dom.js";
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
const RECENT_KEY = "lovktv.recentSearches";
const RECENT_MAX = 10;

/** @returns {string[]} */
export function recentSearches() {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(list) ? list.filter((q) => typeof q === "string" && q).slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

/** @param {string} q */
export function rememberSearch(q) {
  const text = String(q || "").trim();
  if (!text) return;
  const next = [text, ...recentSearches().filter((item) => item.toLowerCase() !== text.toLowerCase())];
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next.slice(0, RECENT_MAX)));
  } catch {
    // Private mode / full storage: recents are a nicety, never block search.
  }
}

export function clearRecentSearches() {
  try {
    localStorage.removeItem(RECENT_KEY);
  } catch {
    // ignore
  }
}

export function searchEmpty() {
  const recent = recentSearches();
  if (recent.length) {
    const chips = recent
      .map((q) => `<button type="button" class="recent-chip" data-recent="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
      .join("");
    return `<section class="recent-searches"><header><h3>${t("phone.search.recent")}</h3><button type="button" class="recent-clear" data-recent-clear>${t("phone.search.recentClear")}</button></header><div class="recent-chips">${chips}</div><p class="tiny recent-hint">${t("phone.search.emptyHint")}</p></section>`;
  }
  return `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.search.empty")}</p><span class="tiny">${t("phone.search.emptyHint")}</span></div>`;
}

/** Shimmer cards shaped like real hits, so results land without a layout jump. */
export function searchSkeleton(n = 8) {
  const card = `<div class="skel-card" aria-hidden="true"><i class="skel skel-art"></i><i class="skel skel-line"></i><i class="skel skel-line short"></i></div>`;
  return `<div class="skel-list" role="status" aria-label="${t("common.searching")}">${card.repeat(n)}</div>`;
}
