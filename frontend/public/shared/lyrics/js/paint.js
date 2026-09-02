import { escapeHtml } from "../../ui/js/dom.js";

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

/** @param {unknown} data */
export function sanitizeLyrics(data) {
  if (!data || typeof data !== "object") return { cues: [] };
  const payload = /** @type {LyricsDoc} */ (data);
  return Object.assign({}, payload, { cues: sanitizeLyricCues(payload.cues) });
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
    .map((tok) => String(tok.romaji || tok.pronunciation?.value || "").trim())
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
    String(tok.romaji || tok.pronunciation?.value || "").trim() || String(tok.translation || tok.zh || "").trim()
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
  el.querySelectorAll(".anno").forEach((anno) => {
    const rb = /** @type {HTMLElement | null} */ (anno.querySelector(".rb"));
    if (!rb) return;
    const box = /** @type {HTMLElement} */ (anno);
    box.style.width = "";
    if (keepPhoneExtraSize) {
      const extras = Array.from(box.querySelectorAll(".roma, .gloss"));
      const sourceWidth = rb.getBoundingClientRect().width;
      let naturalWidth = sourceWidth;
      // Measure the unscaled text before restoring the annotation's minimum
      // width. This gives the token enough room without changing its font.
      extras.forEach((node) => {
        const extra = /** @type {HTMLElement} */ (node);
        extra.style.transform = "";
        extra.style.transformOrigin = "";
        extra.style.width = "max-content";
        extra.style.minWidth = "0";
        naturalWidth = Math.max(naturalWidth, textInkWidth(extra));
      });
      if (naturalWidth > 0) box.style.width = `${Math.ceil(naturalWidth)}px`;
      extras.forEach((node) => {
        /** @type {HTMLElement} */ (node).style.minWidth = "100%";
      });
      return;
    }
    const cap = rb.getBoundingClientRect().width;
    if (cap > 0) box.style.width = `${Math.ceil(cap)}px`;
    box.querySelectorAll(".roma, .gloss").forEach((node) => {
      const extra = /** @type {HTMLElement} */ (node);
      extra.style.transform = "";
      if (cap <= 0) return;
      const w = textInkWidth(extra);
      if (w > cap + 1) {
        extra.style.transform = `scale(${cap / w})`;
        extra.style.transformOrigin = "top center";
      }
    });
  });
}

function fitLyricLine(el) {
  if (tvStage()) return;
  // The listen page owns its responsive lyric sizing. Shrinking each cue to
  // its text width made translated lines appear at different sizes and made
  // long cues overflow narrow phone viewports.
  if (el.closest && el.closest(".player-lyrics")) {
    fitLyricExtras(el);
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

/** @param {LyricCue} cue @param {number} t @param {LyricMode} [mode] */
export function renderCue(cue, t, mode) {
  const view = normLyricMode(mode);
  if (view === "zh") return escapeHtml(String(cue.translation || cue.zh || cueLine(cue)));
  if (view === "roma") return escapeHtml(cueRomaji(cue) || cueLine(cue));
  const tokens = clusterTokens(cue.tokens || []);
  const script = pageLyricScript();
  const showExtra = view === "all";
  const keepRoma = showExtra && (script === "ja" || !script);
  const keepGloss = showExtra;
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
      const latin = /^[A-Za-z0-9']/.test(surface);
      const next = tokens[i + 1];
      const nextSurface = String(next?.surface || next?.text || "");
      const space = latin && next && !/^[.,!?;:'")\]]/.test(nextSurface) ? `<span class="tok-space"> </span>` : "";
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
  const fitKey = `${id}:${Math.round(el.clientWidth)}`;
  if (paint[slot] !== id) {
    el.innerHTML = renderCue(cue, t, view);
    paint[slot] = id;
    el.dataset.lyricFit = "";
  }
  if (el.dataset.lyricFit !== fitKey) {
    fitLyricLine(el);
    if (el.clientWidth > 0) el.dataset.lyricFit = fitKey;
  }
  if (paint[slot] !== id || skin !== "live") return;
  const toks = clusterTokens(cue.tokens || []);
  const fills = el.querySelectorAll(".rb-fill");
  if (!toks.length && fills.length) {
    const next = Math.round(tokenProgress(cue, t)) + "%";
    fills.forEach((node) => {
      const style = /** @type {HTMLElement} */ (node).style;
      if (style.width !== next) style.width = next;
    });
    return;
  }
  fills.forEach((node, i) => {
    if (!toks[i]) return;
    const next = Math.round(tokenProgress(toks[i], t)) + "%";
    const style = /** @type {HTMLElement} */ (node).style;
    if (style.width !== next) style.width = next;
  });
}

/** @param {LyricCue[] | null | undefined} cues @param {number} t */
export function cueIndexAt(cues, t) {
  const list = cues || [];
  const idx = list.findIndex((c) => t >= c.start_ms && t < c.end_ms);
  if (idx >= 0) return idx;
  const upcoming = list.findIndex((c) => t < c.start_ms);
  return upcoming >= 0 ? upcoming : list.length ? list.length - 1 : -1;
}
