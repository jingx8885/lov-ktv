/** @type {ParentNode | null} */
let activeRoot = typeof document !== "undefined" ? document : null;

/**
 * Select the DOM root used by feature modules. Entries call this from their
 * mount(root, deps) boundary so compatibility helpers stay scoped to the app.
 * @param {ParentNode | null | undefined} root
 * @returns {() => void} restore callback
 */
export function setDomRoot(root) {
  const previous = activeRoot;
  activeRoot = root || (typeof document !== "undefined" ? document : null);
  return () => {
    activeRoot = previous;
  };
}

/** @param {string} id @param {ParentNode | null | undefined} [root] @returns {any} */
export const $ = (id, root) => {
  const scope = root || activeRoot;
  if (!scope) return null;
  if (typeof (/** @type {any} */ (scope).getElementById) === "function")
    return /** @type {any} */ (scope).getElementById(id);
  if (!scope.querySelector) return null;
  const escaped =
    typeof CSS !== "undefined" && CSS.escape ? CSS.escape(id) : String(id).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  return scope.querySelector("#" + escaped);
};

/** Shell nodes that must exist. Missing id fails at bind time.
 *  @param {string} id
 *  @returns {any}
 */
export function $must(id, root) {
  const el = $(id, root);
  if (!el) throw new Error("missing #" + id);
  return el;
}

/** @param {unknown} text */
export function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
