export const LYRIC_SIZE_KEY = "tvLyricSizeV2";
export const LYRIC_SIZE_MIN = 10;
export const LYRIC_SIZE_MAX = 250;
export const LYRIC_SIZE_STEP = 10;
export const DEFAULT_LYRIC_SIZE = 30;

const LEGACY_SIZE = {
  s: 80,
  m: 100,
  l: 130,
  xl: 160
};

/** @param {unknown} value */
export function normLyricSize(value) {
  if (value == null || value === "") return DEFAULT_LYRIC_SIZE;
  const raw = String(value).trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(LEGACY_SIZE, raw)) return LEGACY_SIZE[raw];
  const n = Number(raw);
  if (!Number.isFinite(n)) return DEFAULT_LYRIC_SIZE;
  const stepped = Math.round(n / LYRIC_SIZE_STEP) * LYRIC_SIZE_STEP;
  return Math.max(LYRIC_SIZE_MIN, Math.min(LYRIC_SIZE_MAX, stepped));
}

function nativeBridge() {
  try {
    return typeof window !== "undefined" ? window.LovKtvNative : null;
  } catch (_) {
    return null;
  }
}

/** Android TV keeps this outside the page, because the local port can change. */
function nativeLyricSize() {
  const native = nativeBridge();
  if (!native || typeof native.lyricSize !== "function") return "";
  try {
    return String(native.lyricSize() || "");
  } catch (_) {
    return "";
  }
}

function rememberLyricSize(size) {
  const text = String(size);
  try {
    localStorage.setItem(LYRIC_SIZE_KEY, text);
  } catch (_) {}
  const native = nativeBridge();
  if (!native || typeof native.saveLyricSize !== "function") return;
  try {
    native.saveLyricSize(text);
  } catch (_) {}
}

export function storedLyricSize() {
  try {
    const web = localStorage.getItem(LYRIC_SIZE_KEY);
    if (web != null && web !== "") return normLyricSize(web);
  } catch (_) {}
  const native = nativeLyricSize();
  // Old installs persisted the previous 100% default. Ignore that so a
  // fresh page still opens at 30% until the user actually changes it.
  if (native && normLyricSize(native) !== 100) return normLyricSize(native);
  return DEFAULT_LYRIC_SIZE;
}

export function lyricSize() {
  if (typeof document === "undefined" || !document.body) return storedLyricSize();
  const current = document.body.dataset.lyricSize;
  return normLyricSize(current == null || current === "" ? storedLyricSize() : current);
}

function clearFittedSize(el) {
  el.dataset.lyricFit = "";
  el.style.fontSize = "";
  el.style.width = "";
  const words = el.querySelector(".line-words");
  if (!words) return;
  words.style.flexWrap = "";
  words.style.width = "";
}

/** @param {unknown} [value] */
export function applyLyricSize(value) {
  const size = normLyricSize(value == null ? storedLyricSize() : value);
  if (typeof document !== "undefined" && document.body && document.body.dataset.lyricSize === String(size)) {
    return size;
  }
  rememberLyricSize(size);
  if (typeof document !== "undefined" && document.body) {
    document.body.dataset.lyricSize = String(size);
    document.body.style.setProperty("--tv-lyric-scale", String(size / 100));
    ["lyricLeft", "lyricRight"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) clearFittedSize(el);
    });
  }
  return size;
}

/** @param {number} delta steps, usually -1 or 1 */
export function nudgeLyricSize(delta) {
  const step = Number(delta || 0) * LYRIC_SIZE_STEP;
  return applyLyricSize(lyricSize() + step);
}

/** @param {number} [size] */
export function lyricSizeLabel(size) {
  const n = normLyricSize(size == null ? lyricSize() : size);
  return `‹ ${n}% ›`;
}
