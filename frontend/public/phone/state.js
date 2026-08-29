import { guardState } from "../shared/ui/js/guard.js";
import { t } from "../shared/i18n/js/i18n.js";

/** @type {PhoneState} */
export const state = guardState({
  previewId: "",
  searchPage: 1,
  searchHits: [],
  currentPage: "desk",
  libState: { q: "", by: "all", letter: "", page: 1 },
  libTimer: 0,
  libStamp: "",
  libSongs: [],
  libLoading: false,
  libPages: 1,
  searchLoading: false,
  searchHasMore: false,
  playerSong: null,
  playerLyrics: { cues: [] },
  selectedCue: -1,
  lyricsDirty: false,
  playerVocal: localStorage.getItem("playerVocal") === "0" ? 0 : 1,
  songMediaRev: "",
  playerRaf: 0,
  playerHeld: true,
  playerHook: null,
  playerViz: null,
  alignTl: null,
  chainRest: false,
  voiceTrackOn: true,
  mixTrackOn: true,
  playOrder: localStorage.getItem("playOrder") === "shuffle" ? "shuffle" : "seq",
  playerCatalog: [],
  playerLoad: 0,
  playerClockHold: null,
  playerClockHoldAt: 0,
  playerHoldDur: 0,
  lyricPaint: { prev: "", cur: "", next: "", align: "" },
  roomRtc: null,
  roomRtcCode: "",
  mixTimer: 0,
  lyricMode: "all",
  nowLanguage: "",
  phoneMic: null,
  phoneMicSrc: null,
  phoneMicGain: null,
  phoneCtx: null,
  phoneMicLevel: Number(localStorage.getItem("phoneMicGain") || 80),
  phoneIem: localStorage.getItem("phoneIem") !== "0",
  phoneNativeLive: false,
  phoneStartedTv: false,
}, "phone");

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
