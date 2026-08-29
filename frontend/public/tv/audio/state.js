import { guardState } from "../../shared/ui/js/guard.js";

/** Audio, mic and cross-tab coordination ownership. */
export const audioState = guardState(
  {
    tabId: Math.random().toString(36).slice(2),
    audioBus: "BroadcastChannel" in window ? new BroadcastChannel("lovktv-audio") : null,
    isLeader: true,
    audioHook: null,
    stageFx: null,
    lastFxCue: -1,
    lastCelebrateAt: 0,
    hookLines: new Set(),
    pendingMic: null,
    audioUnlocked: false,
    keepAliveTimer: 0,
    keepAliveSrc: "",
    keepAliveTone: null
  },
  "tv.audio"
);
