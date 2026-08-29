import { guardState } from "../../shared/ui/js/guard.js";

/** Mutable state owned by room/session features. */
export const roomState = guardState(
  {
    roomRtc: null,
    roomRtcCode: "",
    mixTimer: 0,
    lyricMode: "all",
    nowLanguage: "",
    phoneNativeLive: false,
    phoneStartedTv: false
  },
  "phone.room"
);
