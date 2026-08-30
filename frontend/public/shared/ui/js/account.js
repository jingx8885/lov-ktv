import { fetchJson } from "./http.js";

/** @param {AuthUser | null | undefined} user */
export function isAccount(user) {
  return !!(user && (user.account || user.username || user.wechat));
}

/**
 * @param {"login" | "register"} mode
 * @param {string} username
 * @param {string} password
 */
export function submitAccount(mode, username, password) {
  const path = mode === "register" ? "/api/auth/register" : "/api/auth/login";
  return fetchJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
}
