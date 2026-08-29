import { guardState } from "../shared/ui/js/guard.js";

/** Platform/session ownership kept separate from room and playback state. */
export const platformState = guardState({}, "tv.platform");
