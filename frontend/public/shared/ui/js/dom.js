/** @param {string} id @returns {any} */
export const $ = (id) => document.getElementById(id);

/** Shell nodes that must exist. Missing id fails at bind time.
 *  @param {string} id
 *  @returns {any}
 */
export function $must(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error("missing #" + id);
  return el;
}

/** @param {unknown} text */
export function escapeHtml(text) {
  return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
