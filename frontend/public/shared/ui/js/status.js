import { t } from "../../i18n/js/i18n.js";

/** @param {string} status */
export function statusLabel(status) {
  return t("status." + status) || status;
}

/** @type {Record<string, string>} */
export const STATUS = new Proxy({}, {
  get(_target, key) {
    if (typeof key !== "string") return undefined;
    return statusLabel(key);
  },
});
