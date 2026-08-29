import zh from "../locales/zh.js?v=mic3";
import yue from "../locales/yue.js?v=mic3";
import en from "../locales/en.js?v=mic3";
import ja from "../locales/ja.js?v=mic3";

export const LOCALES = ["zh", "yue", "en", "ja"];
export const STORAGE_KEY = "lovktv.lang";
export const HTML_LANG = { zh: "zh-CN", yue: "zh-HK", en: "en", ja: "ja" };
export const ACCEPT_LANG = { zh: "zh-CN", yue: "zh-HK", en: "en", ja: "ja" };

const PACKS = { zh, yue, en, ja };
const listeners = new Set();
let current = "zh";
let booted = false;

/** @param {string} raw */
export function parseLang(raw) {
  const text = String(raw || "").trim().toLowerCase();
  if (!text) return "";
  if (LOCALES.includes(text)) return text;
  if (text.startsWith("yue") || text.startsWith("zh-hk") || text.startsWith("zh-mo")) return "yue";
  if (text.startsWith("ja")) return "ja";
  if (text.startsWith("en")) return "en";
  if (text.startsWith("zh")) return "zh";
  return "";
}

function detectLang() {
  try {
    const params = new URLSearchParams(location.search);
    const fromQuery = parseLang(params.get("lang") || "");
    if (fromQuery) return fromQuery;
  } catch (_) {}
  try {
    const stored = parseLang(localStorage.getItem(STORAGE_KEY) || "");
    if (stored) return stored;
  } catch (_) {}
  const nav = (typeof navigator !== "undefined" && (navigator.languages || [navigator.language])) || [];
  for (const item of nav) {
    const hit = parseLang(item);
    if (hit) return hit;
  }
  return "zh";
}

/** @param {string} key @param {Record<string, string|number>} [vars] */
export function t(key, vars) {
  const pack = PACKS[current] || zh;
  let text = pack[key];
  if (text == null) text = zh[key];
  if (text == null) text = key;
  if (vars) {
    text = String(text).replace(/\{(\w+)\}/g, (_, name) => (
      vars[name] == null ? `{${name}}` : String(vars[name])
    ));
  }
  return text;
}

export function lang() {
  return current;
}

export function acceptLanguage() {
  return ACCEPT_LANG[current] || "zh-CN";
}

function syncDocument() {
  if (typeof document === "undefined") return;
  document.documentElement.lang = HTML_LANG[current] || "zh-CN";
  document.documentElement.dataset.lang = current;
}

/** @param {ParentNode} [root] */
export function applyDom(root) {
  const scope = root || document;
  scope.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n") || "");
  });
  scope.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.getAttribute("data-i18n-html") || "");
  });
  scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder") || ""));
  });
  scope.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria") || ""));
  });
  scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
    document.title = t(el.getAttribute("data-i18n-title") || "");
  });
  scope.querySelectorAll("[data-i18n-content]").forEach((el) => {
    el.setAttribute("content", t(el.getAttribute("data-i18n-content") || ""));
  });
  paintLangPicker(scope);
}

function paintLangPicker(root) {
  const scope = root || document;
  scope.querySelectorAll("select.lang-picker").forEach((el) => {
    el.value = current;
  });
  scope.querySelectorAll("[data-set-lang]").forEach((btn) => {
    btn.classList.toggle("on", btn.getAttribute("data-set-lang") === current);
  });
}

/** @param {ParentNode} [root] */
export function bindLangPicker(root) {
  const scope = root || document;
  scope.querySelectorAll("select.lang-picker").forEach((el) => {
    if (el.dataset.langBound) return;
    el.dataset.langBound = "1";
    el.addEventListener("change", () => setLang(el.value || "zh"));
  });
  scope.querySelectorAll("[data-set-lang]").forEach((btn) => {
    if (btn.dataset.langBound) return;
    btn.dataset.langBound = "1";
    btn.addEventListener("click", () => setLang(btn.getAttribute("data-set-lang") || "zh"));
  });
  paintLangPicker(root);
}

/** @param {string} next */
export function setLang(next) {
  const resolved = parseLang(next) || "zh";
  if (resolved === current && booted) {
    applyDom();
    return current;
  }
  current = resolved;
  try {
    localStorage.setItem(STORAGE_KEY, current);
  } catch (_) {}
  syncDocument();
  applyDom();
  listeners.forEach((fn) => fn(current));
  return current;
}

/** @param {(lang: string) => void} fn */
export function onLangChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function bootI18n() {
  current = detectLang();
  try {
    localStorage.setItem(STORAGE_KEY, current);
  } catch (_) {}
  syncDocument();
  applyDom();
  bindLangPicker();
  booted = true;
  if (typeof window !== "undefined") window.LovI18n = api;
  return current;
}

const api = { LOCALES, t, lang, setLang, applyDom, bindLangPicker, onLangChange, acceptLanguage, parseLang, bootI18n };
if (typeof window !== "undefined") window.LovI18n = api;
export default api;
