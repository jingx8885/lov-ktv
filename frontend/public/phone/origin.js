/**
 * Desk can be served from LAN or public. Room queue/skip must stay on the TV box.
 * Catalog/search may use ?process= when m.html is on LAN.
 */

function query() {
  try {
    return new URLSearchParams(location.search || "");
  } catch (err) {
    return new URLSearchParams();
  }
}

function trimOrigin(value) {
  return String(value || "")
    .trim()
    .replace(/\/$/, "");
}

export function lanOrigin() {
  return trimOrigin(query().get("lan"));
}

export function processOrigin() {
  return trimOrigin(query().get("process"));
}

function privateHost(host) {
  const name = String(host || "")
    .trim()
    .toLowerCase();
  if (name === "localhost" || name.endsWith(".local")) return true;
  const parts = name.split(".");
  if (parts.length !== 4) return false;
  const nums = parts.map((part) => Number(part));
  if (nums.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return false;
  if (nums[0] === 192 && nums[1] === 168) return true;
  if (nums[0] === 10) return true;
  if (nums[0] === 172 && nums[1] >= 16 && nums[1] <= 31) return true;
  return false;
}

/** Phone is bound to a TV box, not just a public catalog room. */
export function tvBound() {
  if (processOrigin()) return true;
  if (lanOrigin()) return true;
  try {
    return privateHost(location.hostname);
  } catch (err) {
    return false;
  }
}

function sameOrigin(origin) {
  if (!origin) return true;
  try {
    return new URL(origin).origin === location.origin;
  } catch (err) {
    return false;
  }
}

export function roomUrl(path) {
  const lan = lanOrigin();
  if (!lan || sameOrigin(lan)) return path;
  return lan + (path.charAt(0) === "/" ? path : "/" + path);
}

export function catalogUrl(path) {
  const process = processOrigin();
  if (!process || sameOrigin(process)) return path;
  return process + (path.charAt(0) === "/" ? path : "/" + path);
}

/** Ask the Android phone app to bind the TV LAN URL discovered from the room. */
export function adoptLan(room) {
  const lan = String((room && (room.lan_origin || room.lanOrigin)) || "").replace(/\/$/, "");
  const code = String((room && room.code) || "").toUpperCase();
  if (!lan || !code) return false;
  if (lanOrigin() === lan) return false;
  try {
    if (window.LovKtvPhone && typeof window.LovKtvPhone.useLan === "function") {
      window.LovKtvPhone.useLan(lan, code);
      return true;
    }
  } catch (err) {}
  return false;
}
