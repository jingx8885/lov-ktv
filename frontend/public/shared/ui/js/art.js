import { escapeHtml } from "./dom.js";
import { songTitle } from "./song.js";

/**
 * Song artwork tile. Most catalog songs have no cover yet, so every tile
 * paints a stable gradient + first glyph underneath, and the real cover fades
 * in over it only once it actually loads. A missing cover never flashes a
 * broken image.
 */

// Curated pairs instead of raw hue math: random HSL lands on muddy greens.
const PALETTE = [
  ["#ff6b8f", "#6e1634"],
  ["#9a8cff", "#2b2170"],
  ["#5cc8ff", "#123c66"],
  ["#ffb36b", "#7a2e1a"],
  ["#4fe0b5", "#0f4a46"],
  ["#ff86dc", "#4b1a6b"],
  ["#ffd56b", "#6b4512"],
  ["#7cb8ff", "#3a1f6b"]
];

/** @param {string} text */
function hash(text) {
  let h = 2166136261;
  for (const ch of text) {
    h ^= /** @type {number} */ (ch.codePointAt(0));
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** @param {string} title */
function glyph(title) {
  const match = String(title || "").match(/[\p{L}\p{N}]/u);
  return match ? match[0].toUpperCase() : "♪";
}

/**
 * @param {{ key?: string, title?: string, src?: string, cls?: string, badge?: string, playing?: boolean }} opts
 */
export function artHtml(opts) {
  const title = String(opts.title || "");
  const [a, b] = PALETTE[hash(String(opts.key || title)) % PALETTE.length];
  const img = opts.src
    ? `<img src="${escapeHtml(opts.src)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" />`
    : "";
  const badge = opts.badge ? `<em class="art-badge">${escapeHtml(opts.badge)}</em>` : "";
  const eq = opts.playing ? `<span class="art-eq"><i></i><i></i><i></i></span>` : "";
  return `<span class="art ${opts.cls || ""}" style="--art-a:${a};--art-b:${b}" aria-hidden="true"><b>${escapeHtml(glyph(title))}</b>${img}${badge}${eq}</span>`;
}

/** Cover served next to the song's other media; `media_rev` makes it cacheable. */
export function songCoverUrl(songId, rev) {
  if (!songId) return "";
  return `/media/${encodeURIComponent(songId)}/cover.jpg` + (rev ? `?v=${encodeURIComponent(rev)}` : "");
}

/** @param {any} song @param {{ cls?: string, badge?: string, playing?: boolean }} [opts] */
export function songArt(song, opts = {}) {
  const id = (song && (song.song_id || song.id)) || "";
  return artHtml({
    key: id,
    title: songTitle(song),
    src: songCoverUrl(id, song && song.media_rev),
    ...opts
  });
}

// load/error do not bubble, so one capture listener covers every tile the
// lists re-render instead of inline handlers on each <img>.
if (typeof document !== "undefined") {
  document.addEventListener(
    "load",
    (event) => {
      const img = /** @type {HTMLElement} */ (event.target);
      if (img && img.tagName === "IMG" && img.parentElement?.classList.contains("art")) {
        img.parentElement.classList.add("has-img");
      }
    },
    true
  );
  document.addEventListener(
    "error",
    (event) => {
      const img = /** @type {HTMLElement} */ (event.target);
      if (img && img.tagName === "IMG" && img.parentElement?.classList.contains("art")) img.remove();
    },
    true
  );
}
