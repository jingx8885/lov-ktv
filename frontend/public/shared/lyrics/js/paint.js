import { escapeHtml } from "../../ui/js/dom.js";

export function tokenProgress(tok, t) {
  if (t >= tok.end_ms) return 100;
  if (t >= tok.start_ms) return ((t - tok.start_ms) / Math.max(tok.end_ms - tok.start_ms, 1)) * 100;
  return 0;
}

export function cueKey(cue) {
  return cue ? `${cue.start_ms}:${cue.end_ms}:${cue.text}` : "";
}

export function cueLine(cue) {
  const text = String(cue.text || "");
  const tokens = cue.tokens || [];
  if (/\s/.test(text) || !tokens.length) return text;
  if (tokens.every((tok) => /^[A-Za-z0-9']/.test(tok.text || ""))) {
    return tokens.map((tok) => tok.text).join(" ");
  }
  return text;
}

export function renderCue(cue, t) {
  const tokens = cue.tokens || [];
  if (!tokens.length) return escapeHtml(cueLine(cue));
  return tokens.map((tok, i) => {
    const p = Math.round(tokenProgress(tok, t));
    const body = `<span class="rb" style="--p:${p}%">${escapeHtml(tok.text)}</span>`;
    const reading = tok.reading && tok.reading !== tok.text ? String(tok.reading) : "";
    const rt = `<span class="rt">${[...reading].map((ch) => `<i>${escapeHtml(ch)}</i>`).join("")}</span>`;
    const roma = tok.romaji && tok.romaji !== tok.text ? String(tok.romaji) : "";
    const romaHtml = roma ? `<span class="roma">${escapeHtml(roma)}</span>` : `<span class="roma"></span>`;
    const latin = /^[A-Za-z0-9']/.test(tok.text || "");
    const next = tokens[i + 1];
    const space = latin && next && !/^[.,!?;:'")\]]/.test(next.text || "")
      ? `<span class="tok-space"> </span>`
      : "";
    return `<span class="tok${latin ? " latin" : ""}"><span class="anno">${rt}${body}${romaHtml}</span></span>${space}`;
  }).join("");
}

export function paintLine(el, cue, t, slot, paint, empty) {
  if (!el) return;
  if (!cue) {
    if (paint[slot] !== "empty") {
      el.textContent = empty || "";
      paint[slot] = "empty";
    }
    return;
  }
  const skin = t < 0 ? "wait" : t > 1e10 ? "done" : "live";
  const id = cueKey(cue) + ":" + skin;
  if (paint[slot] !== id) {
    el.innerHTML = renderCue(cue, t);
    paint[slot] = id;
    return;
  }
  if (skin !== "live") return;
  const toks = cue.tokens || [];
  el.querySelectorAll(".rb").forEach((node, i) => {
    if (!toks[i]) return;
    const next = Math.round(tokenProgress(toks[i], t)) + "%";
    if (node.style.getPropertyValue("--p") !== next) node.style.setProperty("--p", next);
  });
}

export function cueIndexAt(cues, t) {
  const list = cues || [];
  const idx = list.findIndex((c) => t >= c.start_ms && t < c.end_ms);
  if (idx >= 0) return idx;
  const upcoming = list.findIndex((c) => t < c.start_ms);
  return upcoming >= 0 ? upcoming : (list.length ? list.length - 1 : -1);
}
