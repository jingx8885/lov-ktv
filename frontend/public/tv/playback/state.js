import { guardState } from "../../shared/ui/js/guard.js";

/** Playback policy and media lifecycle state for the TV player. */
export const playbackState = guardState(
  {
    lyrics: { cues: [] },
    prefetched: new Set(),
    prefetchBusy: 0,
    prefetchWait: [],
    armed: false,
    lyricPaint: { prev: "", cur: "", next: "" },
    lastMtvSeek: 0,
    lastVocalSync: 0,
    boundMtvSong: "",
    skeleton: null,
    playRetryTimer: 0,
    resumeAt: 0,
    resumeSong: "",
    emptyNow: 0,
    mediaStall: 0,
    fallbackSong: "",
    fallbackTrack: "",
    lastRecoverAt: 0,
    lastRoomStamp: ""
  },
  "tv.playback"
);
