import { escapeHtml } from "../../ui/js/dom.js";

/** @type {readonly LyricMode[]} */
export const LYRIC_MODES = ["ja", "zh", "roma", "all"];

/** @param {unknown} value @returns {LyricMode} */
export function normLyricMode(value) {
  const mode = String(value || "").trim();
  return LYRIC_MODES.includes(/** @type {LyricMode} */ (mode)) ? /** @type {LyricMode} */ (mode) : "all";
}

/** @param {HTMLElement | Document} [root] @param {unknown} value */
export function applyLyricMode(root, value) {
  const mode = normLyricMode(value);
  const el = root && "dataset" in root ? root : document.body;
  el.dataset.lyricMode = mode;
  return mode;
}

/** @param {LyricToken} tok @param {number} t */
export function tokenProgress(tok, t) {
  if (t >= tok.end_ms) return 100;
  if (t >= tok.start_ms) return ((t - tok.start_ms) / Math.max(tok.end_ms - tok.start_ms, 1)) * 100;
  return 0;
}

/** @param {LyricCue | null | undefined} cue */
export function cueKey(cue) {
  return cue ? `${cue.start_ms}:${cue.end_ms}:${cue.text}:${cue.zh || ""}` : "";
}

/** @param {LyricCue} cue */
export function cueLine(cue) {
  const text = String(cue.text || "");
  const tokens = cue.tokens || [];
  if (/\s/.test(text) || !tokens.length) return text;
  if (tokens.every((tok) => /^[A-Za-z0-9']/.test(tok.text || ""))) {
    return tokens.map((tok) => tok.text).join(" ");
  }
  return text;
}

/** @param {LyricCue} cue */
export function cueRomaji(cue) {
  const bits = (cue.tokens || []).map((tok) => String(tok.romaji || "").trim()).filter(Boolean);
  return bits.join(" ") || String(cue.romaji || "").trim();
}

/** @param {LyricCue} cue @param {number} t @param {LyricMode} [mode] */
export function renderCue(cue, t, mode) {
  const view = normLyricMode(mode);
  if (view === "zh") return escapeHtml(String(cue.zh || cueLine(cue)));
  if (view === "roma") return escapeHtml(cueRomaji(cue) || cueLine(cue));
  const tokens = cue.tokens || [];
  if (!tokens.length) {
    const body = escapeHtml(cueLine(cue));
    return view === "all" && cue.zh
      ? `${body}<span class="lyric-zh">${escapeHtml(cue.zh)}</span>`
      : body;
  }
  const showExtra = view === "all";
  const html = tokens.map((tok, i) => {
    const p = Math.round(tokenProgress(tok, t));
    const body = `<span class="rb" style="--p:${p}%">${escapeHtml(tok.text)}</span>`;
    const reading = tok.reading && tok.reading !== tok.text ? String(tok.reading) : "";
    const rt = `<span class="rt">${[...reading].map((ch) => `<i>${escapeHtml(ch)}</i>`).join("")}</span>`;
    const roma = showExtra && tok.romaji && tok.romaji !== tok.text ? String(tok.romaji) : "";
    const romaHtml = roma ? `<span class="roma">${escapeHtml(roma)}</span>` : `<span class="roma"></span>`;
    const gloss = showExtra && tok.zh ? String(tok.zh) : "";
    const glossHtml = gloss ? `<span class="gloss">${escapeHtml(gloss)}</span>` : `<span class="gloss"></span>`;
    const latin = /^[A-Za-z0-9']/.test(tok.text || "");
    const next = tokens[i + 1];
    const space = latin && next && !/^[.,!?;:'")\]]/.test(next.text || "")
      ? `<span class="tok-space"> </span>`
      : "";
    return `<span class="tok${latin ? " latin" : ""}"><span class="anno">${rt}${body}${romaHtml}${glossHtml}</span></span>${space}`;
  }).join("");
  return showExtra && cue.zh
    ? `${html}<span class="lyric-zh">${escapeHtml(cue.zh)}</span>`
    : html;
}

/**
 * @param {HTMLElement | null} el
 * @param {LyricCue | null | undefined} cue
 * @param {number} t
 * @param {keyof LyricPaintSlots | string} slot
 * @param {LyricPaintSlots} paint
 * @param {string} [empty]
 * @param {LyricMode | string} [mode]
 */
export function paintLine(el, cue, t, slot, paint, empty, mode) {
  if (!el) return;
  const view = normLyricMode(mode);
  if (!cue) {
    const blank = `empty:${view}`;
    if (paint[slot] !== blank) {
      el.textContent = empty || "";
      paint[slot] = blank;
    }
    return;
  }
  const skin = t < 0 ? "wait" : t > 1e10 ? "done" : "live";
  const id = cueKey(cue) + ":" + skin + ":" + view;
  if (paint[slot] !== id) {
    el.innerHTML = renderCue(cue, t, view);
    paint[slot] = id;
    return;
  }
  if (skin !== "live") return;
  const toks = cue.tokens || [];
  el.querySelectorAll(".rb").forEach((node, i) => {
    if (!toks[i]) return;
    const next = Math.round(tokenProgress(toks[i], t)) + "%";
    const style = /** @type {HTMLElement} */ (node).style;
    if (style.getPropertyValue("--p") !== next) style.setProperty("--p", next);
  });
}

/** @param {LyricCue[] | null | undefined} cues @param {number} t */
export function cueIndexAt(cues, t) {
  const list = cues || [];
  const idx = list.findIndex((c) => t >= c.start_ms && t < c.end_ms);
  if (idx >= 0) return idx;
  const upcoming = list.findIndex((c) => t < c.start_ms);
  return upcoming >= 0 ? upcoming : (list.length ? list.length - 1 : -1);
}
