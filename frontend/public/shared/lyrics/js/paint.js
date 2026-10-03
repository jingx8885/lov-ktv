import { escapeHtml } from "../../ui/js/dom.js";
import { lang } from "../../i18n/js/i18n.js";

/** @type {readonly LyricMode[]} */
export const LYRIC_MODES = ["ja", "zh", "roma", "all"];

/** @param {unknown} value @returns {LyricMode} */
export function normLyricMode(value) {
  const mode = String(value || "").trim();
  return LYRIC_MODES.includes(/** @type {LyricMode} */ (mode)) ? /** @type {LyricMode} */ (mode) : "all";
}

/** @param {unknown} [language] */
export function lyricScript(language) {
  const lang = String(language || "")
    .trim()
    .toLowerCase();
  if (!lang) return "";
  if (lang === "ja" || lang.startsWith("ja-")) return "ja";
  if (lang === "en" || lang.startsWith("en-")) return "en";
  if (lang === "yue" || lang.startsWith("zh")) return "zh";
  return lang;
}

/** @param {unknown} mode @param {string} script */
export function lyricModeForScript(mode, script) {
  const next = normLyricMode(mode);
  if (script === "zh") return "all";
  if (next === "roma" && script === "en") return "all";
  if (next === "roma" && script && script !== "ja") return "ja";
  return next;
}

/** @param {HTMLElement | Document} [root] @param {unknown} [value] @param {string} [language] */
export function applyLyricMode(root, value, language) {
  const el = root && "dataset" in root ? root : document.body;
  const script = language !== undefined ? lyricScript(language) : String(el.dataset.lyricScript || "");
  const mode = lyricModeForScript(value, script);
  el.dataset.lyricMode = mode;
  if (language !== undefined) el.dataset.lyricScript = script;
  return mode;
}

/** @param {LyricToken} tok @param {number} t */
export function tokenProgress(tok, t) {
  if (t >= tok.end_ms) return 100;
  if (t >= tok.start_ms) return ((t - tok.start_ms) / Math.max(tok.end_ms - tok.start_ms, 1)) * 100;
  return 0;
}

// Layout reads in the paint path dirty the frame when they run against fresh
// style writes. Lines are re-measured only when their content, the lyric size
// setting, or a viewport epoch changes instead of on every frame.
let lyricFitEpoch = 0;
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  const bumpLyricFit = () => {
    lyricFitEpoch += 1;
  };
  window.addEventListener("resize", bumpLyricFit);
  window.addEventListener("orientationchange", bumpLyricFit);
  if (typeof document !== "undefined" && document.fonts && document.fonts.ready) {
    document.fonts.ready.then(bumpLyricFit).catch(() => {});
  }
}

const LEADING_STAMPS = /^(?:\s*\[\d+:\d+(?:\.\d+)?\])+/;
const STAMP_ONLY = /^(?:\[\d+:\d+(?:\.\d+)?\]\s*)+$/;

/** @param {unknown} text */
export function stampOnlyLyric(text) {
  const body = String(text || "").trim();
  return !body || STAMP_ONLY.test(body);
}

/** @param {unknown} text */
export function stripLyricStamps(text) {
  return String(text || "")
    .replace(LEADING_STAMPS, "")
    .trim();
}

/** @param {LyricCue[] | null | undefined} cues */
export function sanitizeLyricCues(cues) {
  const out = [];
  for (const cue of cues || []) {
    const raw = String(cue.text || "");
    if (stampOnlyLyric(raw)) continue;
    const text = stripLyricStamps(raw);
    if (!text || stampOnlyLyric(text)) continue;
    const next = Object.assign({}, cue, {
      text,
      surface: String(cue.surface || text),
      translation: String(cue.translation || cue.zh || ""),
      tokens: (cue.tokens || []).map((token) => {
        const surface = String(token.surface || token.text || "");
        const translation = String(token.translation || token.zh || "");
        const pronunciation =
          token.pronunciation && typeof token.pronunciation === "object"
            ? token.pronunciation
            : token.romaji
              ? { system: "romaji", value: String(token.romaji) }
              : {};
        return Object.assign({}, token, {
          text: surface,
          surface,
          translation,
          zh: translation,
          pronunciation
        });
      })
    });
    if (next.translation) next.translation = stripLyricStamps(next.translation);
    next.zh = next.translation;
    out.push(next);
  }
  return out;
}

function applySupplementalTranslation(payload, cues) {
  const current = lang();
  const target = current === "yue" ? "zh" : current;
  const rows = payload && payload.translations && payload.translations[target];
  if (!Array.isArray(rows)) return cues;
  return cues.map((cue, index) => {
    const row = rows[index];
    if (!row) return cue;
    const tokens = (cue.tokens || []).map((token, tokenIndex) => {
      const extra = row.tokens && row.tokens[tokenIndex];
      return extra && extra.translation
        ? Object.assign({}, token, { translation: extra.translation, zh: extra.translation })
        : token;
    });
    const translation = String(row.translation || "");
    return translation
      ? Object.assign({}, cue, { translation, zh: translation, tokens })
      : Object.assign({}, cue, { tokens });
  });
}

/** @param {unknown} data */
export function sanitizeLyrics(data) {
  if (!data || typeof data !== "object") return { cues: [] };
  const payload = /** @type {LyricsDoc} */ (data);
  const cues = sanitizeLyricCues(payload.cues);
  return Object.assign({}, payload, { cues: applySupplementalTranslation(payload, cues) });
}

/** @param {LyricCue | null | undefined} cue */
export function cueKey(cue) {
  return cue ? `${cue.start_ms}:${cue.end_ms}:${cue.text}:${cue.translation || cue.zh || ""}` : "";
}

/** @param {LyricCue} cue */
export function cueLine(cue) {
  const text = String(cue.text || "");
  const tokens = cue.tokens || [];
  if (/\s/.test(text) || !tokens.length) return text;
  if (tokens.every((tok) => /^[A-Za-z0-9']/.test(tok.surface || tok.text || ""))) {
    return tokens.map((tok) => tok.surface || tok.text).join(" ");
  }
  return text;
}

/** @param {LyricCue} cue */
export function cueRomaji(cue) {
  const bits = (cue.tokens || [])
    .map((tok) => String(tok.romaji || (tok.pronunciation && tok.pronunciation.value) || "").trim())
    .filter(Boolean);
  return bits.join(" ") || String(cue.romaji || "").trim();
}

function isKanaText(value) {
  return /^[\u3040-\u30ffーゝゞ]+$/.test(String(value || ""));
}

function isKanjiText(value) {
  return /[\u4e00-\u9fff]/.test(String(value || ""));
}

function tokenHasAnno(tok) {
  return !!(
    String(tok.romaji || (tok.pronunciation && tok.pronunciation.value) || "").trim() ||
    String(tok.translation || tok.zh || "").trim()
  );
}

/** Merge per-kana pieces so romaji / gloss sit under the whole sung word. */
export function clusterTokens(tokens) {
  const out = [];
  for (const tok of tokens || []) {
    const cur = Object.assign({}, tok, { text: String(tok.text || "") });
    const prev = out[out.length - 1];
    const join = prev && isKanaText(prev.text) && isKanaText(cur.text) && tokenHasAnno(prev) && !tokenHasAnno(cur);
    if (join) {
      prev.text += cur.text;
      prev.end_ms = cur.end_ms;
      continue;
    }
    out.push(cur);
  }
  return out;
}

function textInkWidth(node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  return range.getBoundingClientRect().width;
}

function tvStage() {
  return typeof document !== "undefined" && !!(document.body && document.body.classList.contains("tv"));
}

function fitLyricExtras(el) {
  if (tvStage()) return;
  // On the phone player each token's gloss must keep the same optical size.
  // Scaling a long gloss down to the source token width made neighboring
  // words visibly jump between different font sizes. Let the annotation use
  // its natural width instead; the lyric line's wrapping handles the result.
  const keepPhoneExtraSize = !!(el.closest && el.closest(".player-lyrics"));
  const jobs = [];
  // Phase 1 clears every constraint. The measurements in phase 2 then share
  // one layout pass instead of forcing a fresh one per annotation, which is
  // what made lyric line changes hitch on mobile WebViews.
  el.querySelectorAll(".anno").forEach((anno) => {
    const box = anno;
    box.style.width = "";
    const rb = box.querySelector(".rb");
    if (!rb) return;
    const extras = Array.from(box.querySelectorAll(".roma, .gloss"));
    extras.forEach((node) => {
      node.style.transform = "";
      node.style.transformOrigin = "";
      if (keepPhoneExtraSize) {
        node.style.width = "max-content";
        node.style.minWidth = "0";
      }
    });
    jobs.push({ box, rb, extras, cap: 0, widths: [] });
  });
  jobs.forEach((job) => {
    job.cap = job.rb.getBoundingClientRect().width;
    job.widths = job.extras.map((extra) => textInkWidth(extra));
  });
  jobs.forEach((job) => {
    if (keepPhoneExtraSize) {
      let naturalWidth = job.cap;
      job.widths.forEach((w) => {
        naturalWidth = Math.max(naturalWidth, w);
      });
      if (naturalWidth > 0) job.box.style.width = Math.ceil(naturalWidth) + "px";
      job.extras.forEach((node) => {
        node.style.minWidth = "100%";
      });
      return;
    }
    const cap = job.cap;
    if (cap > 0) job.box.style.width = Math.ceil(cap) + "px";
    job.extras.forEach((node, i) => {
      if (cap <= 0) return;
      const w = job.widths[i];
      if (w > cap + 1) {
        node.style.transform = "scale(" + cap / w + ")";
        node.style.transformOrigin = "top center";
      }
    });
  });
}

function tvLineMaxWidth(box) {
  const parent = box.parentElement;
  const plate = parent && parent.clientWidth ? parent.clientWidth : 0;
  const style = getComputedStyle(box);
  const pad = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
  return Math.floor(Math.max(0, plate - pad - 8));
}

function contentInkWidth(box, content) {
  const boxMax = box.style.maxWidth;
  const contentMax = content.style.maxWidth;
  box.style.maxWidth = "none";
  content.style.maxWidth = "none";
  const width = Math.ceil(content.scrollWidth);
  box.style.maxWidth = boxMax;
  content.style.maxWidth = contentMax;
  return width;
}

function widestToken(content) {
  const nodes = content.querySelectorAll(".tok, .rb");
  let max = 0;
  nodes.forEach((node) => {
    max = Math.max(max, Math.ceil(node.getBoundingClientRect().width));
  });
  return max || Math.ceil(content.scrollWidth);
}

/** Pixel size for the TV subtitle. Old WebViews drop clamp(), so the setting is applied directly. */
function tvLyricFontPx() {
  const raw = document.body && document.body.dataset.lyricSize;
  const n = Number(raw);
  const scale = Number.isFinite(n) && n > 0 ? n / 100 : 0.3;
  return Math.round(64 * scale);
}

function fitTvLyricLine(box) {
  const chosen = tvLyricFontPx();
  box.style.fontSize = `${chosen}px`;
  box.style.width = "";
  const words = box.querySelector(".line-words");
  if (words) {
    words.style.flexWrap = "";
    words.style.width = "";
  }
  const content = words || box.querySelector(".rb");
  if (!content) return;
  const maxW = tvLineMaxWidth(box);
  if (maxW <= 0) return;
  if (contentInkWidth(box, content) <= maxW + 1) return;
  // Long cues wrap at the chosen size. Shrinking them back onto one line
  // made every size setting land on the same fitted width. max-width also
  // clamps scrollWidth, so the overflow check has to use the uncapped ink.
  box.style.width = "100%";
  if (words) {
    words.style.flexWrap = "wrap";
    words.style.width = "100%";
  }
  let size = chosen;
  const min = Math.min(chosen, Math.max(4, chosen * 0.85));
  for (let i = 0; i < 3 && widestToken(content) > maxW + 8 && size > min + 0.5; i += 1) {
    const need = widestToken(content);
    size = Math.max(min, size * (maxW / Math.max(need, 1)) * 0.98);
    box.style.fontSize = `${size.toFixed(2)}px`;
  }
}

function fitLyricLine(el) {
  // The listen page owns its responsive lyric sizing. Shrinking each cue to
  // its text width made translated lines appear at different sizes and made
  // long cues overflow narrow phone viewports.
  if (el.closest && el.closest(".player-lyrics")) {
    fitLyricExtras(el);
    return;
  }
  if (tvStage()) {
    const box = /** @type {HTMLElement} */ (el);
    fitTvLyricLine(box);
    if (document.fonts && document.fonts.status !== "loaded") {
      document.fonts.ready.then(() => fitTvLyricLine(box));
    }
    return;
  }
  const run = () => {
    const box = /** @type {HTMLElement} */ (el);
    box.style.fontSize = "";
    box.querySelectorAll(".anno").forEach((anno) => {
      /** @type {HTMLElement} */ (anno).style.width = "";
    });
    const words = box.querySelector(".line-words");
    const content = words || box.querySelector(".rb");
    if (!content) return;
    fitLyricExtras(box);
    const maxW = box.clientWidth;
    if (maxW <= 0) return;
    const needW = content.scrollWidth;
    if (needW <= maxW + 1) return;
    const base = parseFloat(getComputedStyle(box).fontSize) || 24;
    const next = Math.max(14, base * (maxW / needW) * 0.98);
    box.style.fontSize = `${next.toFixed(2)}px`;
    fitLyricExtras(box);
    const again = content.scrollWidth;
    if (again > maxW + 1) {
      const retry = Math.max(14, next * (maxW / again) * 0.97);
      box.style.fontSize = `${retry.toFixed(2)}px`;
      fitLyricExtras(box);
    }
  };
  run();
  if (document.fonts && document.fonts.status !== "loaded") {
    document.fonts.ready.then(run);
  }
}

function pageLyricScript() {
  if (typeof document === "undefined" || !document.body) return "";
  return String(document.body.dataset.lyricScript || "");
}

function tokenRoma(tok) {
  const script = pageLyricScript();
  if (script && script !== "ja") return "";
  const pronunciation = tok.pronunciation && tok.pronunciation.system === "romaji" ? tok.pronunciation.value : "";
  const roma = String(tok.romaji || pronunciation || "").trim();
  const text = String(tok.surface || tok.text || "");
  if (!roma || roma === text) return "";
  if (/^[A-Za-z0-9']/.test(text) && roma.toLowerCase() === text.toLowerCase()) return "";
  return roma;
}

function rubyHtml(tok, keepRow) {
  const reading = tok.reading && tok.reading !== tok.text ? String(tok.reading) : "";
  if (reading && isKanjiText(tok.text) && !isKanjiText(reading)) {
    return `<span class="rt">${Array.from(reading)
      .map((ch) => `<i>${escapeHtml(ch)}</i>`)
      .join("")}</span>`;
  }
  return keepRow ? `<span class="rt"></span>` : "";
}

function karaokeSpan(text, p) {
  const safe = escapeHtml(text);
  return `<span class="rb"><span class="rb-base">${safe}</span><span class="rb-fill" style="width:${p}%">${safe}</span></span>`;
}

function isLatinSurface(text) {
  return /^[A-Za-z0-9']/.test(String(text || ""));
}

/** Insert a word gap only between Latin tokens, or at a CJK/Latin boundary. */
function tokenGapHtml(surface, nextSurface, script) {
  if (!nextSurface) return "";
  if (/^[.,!?;:'")\]]/.test(nextSurface)) return "";
  const latin = isLatinSurface(surface);
  const nextLatin = isLatinSurface(nextSurface);
  if (latin && nextLatin) return `<span class="tok-space"> </span>`;
  if (script === "zh" && latin !== nextLatin) return `<span class="tok-space"> </span>`;
  return "";
}

/** @param {LyricCue} cue @param {number} t @param {LyricMode} [mode] */
export function renderCue(cue, t, mode) {
  const view = normLyricMode(mode);
  if (view === "zh") return escapeHtml(String(cue.translation || cue.zh || cueLine(cue)));
  if (view === "roma") return escapeHtml(cueRomaji(cue) || cueLine(cue));
  const tokens = clusterTokens(cue.tokens || []);
  const script = pageLyricScript();
  const showExtra = view === "all";
  const keepRoma = showExtra && (script === "ja" || !script);
  // Chinese / Cantonese keep a single line translation; per-character gloss
  // would both invent a fake word row and shove a gap between every Han.
  const keepGloss = showExtra && script !== "zh";
  const keepZh = showExtra;
  // Japanese mode keeps the source line readable with furigana, while the
  // complete view mirrors the TV subtitle stack. Other scripts do not have
  // Japanese readings to display.
  const keepRt = (view === "ja" || showExtra) && (script === "ja" || !script);
  if (!tokens.length) {
    const body = karaokeSpan(cueLine(cue), Math.round(tokenProgress(cue, t)));
    const translation = cue.translation || cue.zh || "";
    return keepZh ? `${body}<span class="lyric-zh">${escapeHtml(String(translation))}</span>` : body;
  }
  const html = `<span class="line-words">${tokens
    .map((tok, i) => {
      const p = Math.round(tokenProgress(tok, t));
      const surface = String(tok.surface || tok.text || "");
      const body = karaokeSpan(surface, p);
      const roma = keepRoma ? tokenRoma(tok) : "";
      const romaHtml = keepRoma ? `<span class="roma">${escapeHtml(roma)}</span>` : "";
      const gloss = keepGloss ? String(tok.translation || tok.zh || "") : "";
      const glossHtml = keepGloss ? `<span class="gloss">${escapeHtml(gloss)}</span>` : "";
      const latin = isLatinSurface(surface);
      const next = tokens[i + 1];
      const nextSurface = String((next && (next.surface || next.text)) || "");
      const space = tokenGapHtml(surface, nextSurface, script);
      return `<span class="tok${latin ? " latin" : ""}"><span class="anno">${rubyHtml(tok, keepRt)}${body}${romaHtml}${glossHtml}</span></span>${space}`;
    })
    .join("")}</span>`;
  return keepZh ? `${html}<span class="lyric-zh">${escapeHtml(String(cue.zh || ""))}</span>` : html;
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
export function syncLine(el, cue, t, slot, paint, empty, mode) {
  if (!el) return false;
  const view = normLyricMode(mode);
  if (!cue) {
    const blank = "empty:" + view;
    if (paint[slot] !== blank) {
      el.textContent = empty || "";
      paint[slot] = blank;
      paint[slot + "~fills"] = null;
    }
    return false;
  }
  const skin = t < 0 ? "wait" : t > 1e10 ? "done" : "live";
  const id = cueKey(cue) + ":" + skin + ":" + view;
  const sizeKey = typeof document !== "undefined" && document.body ? String(document.body.dataset.lyricSize || "") : "";
  const fitKey = id + ":" + sizeKey + ":" + lyricFitEpoch;
  if (paint[slot] !== id) {
    el.innerHTML = renderCue(cue, t, view);
    paint[slot] = id;
    el.dataset.lyricFit = "";
    paint[slot + "~fills"] = null;
  }
  if (el.dataset.lyricFit !== fitKey) {
    fitLyricLine(el);
    if (el.clientWidth > 0) el.dataset.lyricFit = fitKey;
  }
  return skin === "live";
}

/**
 * Writes karaoke progress widths only. The token list and fill nodes are
 * cached per slot so a steady-state frame performs no querySelectorAll and
 * no clusterTokens allocation. The align editor mutates cue tokens without
 * changing cue identity, so it bypasses the cache.
 * @param {HTMLElement | null} el
 * @param {LyricCue} cue
 * @param {number} t
 * @param {keyof LyricPaintSlots | string} slot
 * @param {LyricPaintSlots} paint
 */
export function updateLineFills(el, cue, t, slot, paint) {
  if (!el || !cue) return;
  const editing = !!(typeof document !== "undefined" && document.body && document.body.classList.contains("edit-on"));
  let cache = editing ? null : paint[slot + "~fills"];
  if (!cache) {
    cache = {
      toks: clusterTokens(cue.tokens || []),
      fills: Array.from(el.querySelectorAll(".rb-fill"))
    };
    paint[slot + "~fills"] = cache;
  }
  if (!cache.toks.length) {
    if (!cache.fills.length) return;
    const next = Math.round(tokenProgress(cue, t) * 10) / 10 + "%";
    cache.fills.forEach((node) => {
      const style = node.style;
      if (style.width !== next) style.width = next;
    });
    return;
  }
  cache.fills.forEach((node, i) => {
    const tok = cache.toks[i];
    if (!tok) return;
    const next = Math.round(tokenProgress(tok, t) * 10) / 10 + "%";
    const style = node.style;
    if (style.width !== next) style.width = next;
  });
}

export function paintLine(el, cue, t, slot, paint, empty, mode) {
  if (syncLine(el, cue, t, slot, paint, empty, mode)) updateLineFills(el, cue, t, slot, paint);
}

/** @param {LyricCue[] | null | undefined} cues @param {number} t */
export function cueIndexAt(cues, t) {
  const list = cues || [];
  if (!list.length) return -1;
  // Last cue starting at or before t. The previous pair of findIndex scans
  // walked the whole document on every paint frame; a binary search keeps
  // the lookup at log(n).
  let lo = 0;
  let hi = list.length - 1;
  let at = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid].start_ms <= t) {
      at = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  if (at < 0) return 0;
  if (t >= list[at].end_ms) return Math.min(at + 1, list.length - 1);
  // Overlapping cues still resolve to the first covering line.
  while (at > 0 && list[at - 1].end_ms > t && list[at - 1].start_ms <= t) at -= 1;
  return at;
}
