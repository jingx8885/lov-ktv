/**
 * Android TV bridge adapter. Feature modules use capability-shaped helpers
 * instead of reaching into the untyped WebView global directly.
 */
function bridge() {
  try {
    return typeof window !== "undefined" ? /** @type {any} */ (window).LovKtvNative : null;
  } catch (err) {
    return null;
  }
}

export function nativeMtvAvailable() {
  const native = bridge();
  return !!(native && typeof native.playMtv === "function");
}

export function playNativeMtv(url) {
  const native = bridge();
  if (!native || typeof native.playMtv !== "function") return false;
  try {
    native.playMtv(String(url || ""));
    return true;
  } catch (err) {
    return false;
  }
}

export function stopNativeMtv() {
  const native = bridge();
  if (!native || typeof native.stopMtv !== "function") return false;
  try {
    native.stopMtv();
    return true;
  } catch (err) {
    return false;
  }
}

export function clearNativeLyrics() {
  const native = bridge();
  if (!native || typeof native.clearLyrics !== "function") return false;
  try {
    native.clearLyrics();
    return true;
  } catch (err) {
    return false;
  }
}

export function pauseNativeMtv() {
  const native = bridge();
  if (!native || typeof native.pauseMtv !== "function") return false;
  try {
    native.pauseMtv();
    return true;
  } catch (err) {
    return false;
  }
}

export function resumeNativeMtv() {
  const native = bridge();
  if (!native || typeof native.resumeMtv !== "function") return false;
  try {
    native.resumeMtv();
    return true;
  } catch (err) {
    return false;
  }
}

export function nativeMtvDurationMs() {
  const native = bridge();
  if (!native || typeof native.durationMs !== "function") return 0;
  try {
    return Number(native.durationMs()) || 0;
  } catch (err) {
    return 0;
  }
}

export function nativeMtvPositionMs() {
  const native = bridge();
  if (!native || typeof native.positionMs !== "function") return 0;
  try {
    return Number(native.positionMs()) || 0;
  } catch (err) {
    return 0;
  }
}

export function nativeMtvPlaying() {
  const native = bridge();
  if (!native || typeof native.playing !== "function") return true;
  try {
    return !!native.playing();
  } catch (err) {
    return true;
  }
}

export function seekNativeMtv(positionMs) {
  const native = bridge();
  if (!native || typeof native.seekMtv !== "function") return false;
  try {
    native.seekMtv(Number(positionMs) || 0);
    return true;
  } catch (err) {
    return false;
  }
}

export function openNativeSetup() {
  const native = bridge();
  if (!native || typeof native.openSetup !== "function") return false;
  try {
    native.openSetup();
    return true;
  } catch (err) {
    return false;
  }
}

export function nativeSetupAvailable() {
  const native = bridge();
  return !!(native && typeof native.openSetup === "function");
}

export function hasNativeTv() {
  return !!bridge();
}

/** Named ports keep browser and Android-TV playback on one capability shape. */
export const tvPlatform = {
  http: { available: () => true, fetchJson: null },
  media: { url: (path) => String(path || "") },
  mic: { available: hasNativeTv },
  remote: { available: hasNativeTv },
  scanner: { available: () => false }
};
