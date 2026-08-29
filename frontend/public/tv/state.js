import { guardState } from "../shared/ui/js/guard.js";

/** @type {TvState} */
export const state = guardState(
  {
    room: null,
    lyrics: { cues: [] },
    lastItem: "",
    prefetched: new Set(),
    prefetchBusy: 0,
    prefetchWait: [],
    armed: false,
    tabId: Math.random().toString(36).slice(2),
    audioBus: "BroadcastChannel" in window ? new BroadcastChannel("lovktv-audio") : null,
    isLeader: true,
    lastLyricsAt: 0,
    lastMediaRev: "",
    lyricPaint: { prev: "", cur: "", next: "" },
    audioHook: null,
    stageFx: null,
    lastFxCue: -1,
    lastCelebrateAt: 0,
    hookLines: new Set(),
    roomRtc: null,
    lastMtvSeek: 0,
    lastVocalSync: 0,
    boundMtvSong: "",
    skeleton: null,
    loginTicket: "",
    loginTimer: 0,
    pendingMic: null,
    audioUnlocked: false,
    keepAliveTimer: 0,
    keepAliveSrc: "",
    keepAliveTone: null,
    playRetryTimer: 0,
    resumeAt: 0,
    emptyNow: 0,
    mediaStall: 0,
    mediaFallback: "",
    lastRecoverAt: 0
  },
  "tv"
);
