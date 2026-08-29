import { guardState } from "../../shared/ui/js/guard.js";

/** Room snapshot and WebSocket ownership for the TV runtime. */
export const roomState = guardState(
  {
    room: null,
    roomRtc: null,
    lastItem: "",
    lastMediaRev: "",
    lastLyricsAt: 0,
    loginTicket: "",
    loginTimer: 0,
    hostPollTimer: 0
  },
  "tv.room"
);
