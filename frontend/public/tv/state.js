import { guardState } from "../shared/ui/js/guard.js";
import { roomState } from "./room/state.js";
import { playbackState } from "./playback/state.js";
import { audioState } from "./audio/state.js";
import { platformState } from "./platform-state.js";

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

const tvState = {};
ownSlice(tvState, roomState);
ownSlice(tvState, playbackState);
ownSlice(tvState, audioState);
ownSlice(tvState, platformState);

/** @type {TvState} */
/** Compatibility facade; ownership lives in the room/playback/audio slices. */
export const state = guardState(tvState, "tv");
export { roomState, playbackState, audioState, platformState };
