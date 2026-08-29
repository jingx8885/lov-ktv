import {
  hasNativeMic as platformHasNativeMic,
  nativeCapabilities,
  nativeMicState,
  setNativeGain,
  nativeCall
} from "../../../platform.js";

// Explicit wrappers preserve the original feature-module API while routing
// all calls through the centralized platform boundary.
// Native bridge method: startTvMic (invoked through nativeCall), bridge.startTvMic.
export function hasNativeMic() {
  return platformHasNativeMic();
}

export { nativeCapabilities, nativeMicState, setNativeGain, nativeCall };

export const nativeCaps = nativeCapabilities;
