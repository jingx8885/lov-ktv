import { guardState } from "../../shared/ui/js/guard.js";

/** Mutable state owned by playback, microphone and learning features. */
export const playerState = guardState(
  {
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
    lyricPaint: { prev: "", cur: "", next: "", align: "", scroll: { prev: "", cur: "", next: "" } },
    phoneMic: null,
    phoneMicSrc: null,
    phoneMicGain: null,
    phoneCtx: null,
    phoneMicLevel: Number(localStorage.getItem("phoneMicGain") || 80),
    phoneIem: localStorage.getItem("phoneIem") !== "0"
  },
  "phone.player"
);
