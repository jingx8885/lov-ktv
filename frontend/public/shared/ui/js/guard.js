/**
 * @template {Record<string, any>} T
 * @param {T} value
 * @param {string} label
 * @returns {T}
 */
export function guardState(value, label) {
  const keys = new Set(Object.keys(value));
  return new Proxy(value, {
    set(target, key, next) {
      if (typeof key === "string" && !keys.has(key)) {
        throw new Error("unknown " + label + " state: " + key);
      }
      /** @type {any} */ (target)[key] = next;
      return true;
    }
  });
}
