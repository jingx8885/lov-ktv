import { t } from "../../../../shared/i18n/js/i18n.js";

export const LYRIC_SIZES = ["s", "m", "l", "xl"];
export const LYRIC_SIZE_KEY = "tvLyricSize";
export const DEFAULT_LYRIC_SIZE = "m";

const SIZE_LABEL = {
  s: "tv.lyricSizeS",
  m: "tv.lyricSizeM",
  l: "tv.lyricSizeL",
  xl: "tv.lyricSizeXl"
};

/** @param {unknown} value */
export function normLyricSize(value) {
  const size = String(value || "")
    .trim()
    .toLowerCase();
  return LYRIC_SIZES.includes(size) ? size : DEFAULT_LYRIC_SIZE;
}

export function storedLyricSize() {
  try {
    return normLyricSize(localStorage.getItem(LYRIC_SIZE_KEY));
  } catch (_) {
    return DEFAULT_LYRIC_SIZE;
  }
}

export function lyricSize() {
  if (typeof document === "undefined" || !document.body) return storedLyricSize();
  return normLyricSize(document.body.dataset.lyricSize || storedLyricSize());
}

/** @param {unknown} [value] */
export function applyLyricSize(value) {
  const size = normLyricSize(value == null ? storedLyricSize() : value);
  try {
    localStorage.setItem(LYRIC_SIZE_KEY, size);
  } catch (_) {}
  if (typeof document !== "undefined" && document.body) {
    document.body.dataset.lyricSize = size;
    ["lyricLeft", "lyricRight"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.dataset.lyricFit = "";
      el.style.fontSize = "";
    });
  }
  return size;
}

/** @param {number} delta */
export function nudgeLyricSize(delta) {
  const sizes = LYRIC_SIZES;
  const index = sizes.indexOf(lyricSize());
  const next = Math.max(0, Math.min(sizes.length - 1, index + Number(delta || 0)));
  return applyLyricSize(sizes[next]);
}

export function cycleLyricSize() {
  const sizes = LYRIC_SIZES;
  const index = sizes.indexOf(lyricSize());
  return applyLyricSize(sizes[(index + 1) % sizes.length]);
}

/** @param {string} [size] */
export function lyricSizeLabel(size) {
  const key = SIZE_LABEL[normLyricSize(size || lyricSize())] || SIZE_LABEL.m;
  return `‹ ${t(key)} ›`;
}
