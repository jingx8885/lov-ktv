import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { lanOrigin, roomUrl, tvBound } from "../../origin.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { api } from "../../api.js";
import { paintTopRoom } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { closeOverlay, openOverlay } from "../../ui/js/overlays.js";

export function hasNativeScan() {
  try {
    return typeof window.LovKtvPhone !== "undefined" && typeof window.LovKtvPhone.scanTv === "function";
  } catch (err) {
    return false;
  }
}

export function scanTv() {
  if (!hasNativeScan()) return false;
  window.LovKtvPhone.scanTv();
  return true;
}

/** @returns {boolean} true if a TV bind was requested and the caller should stop. */
export function requestTvBind() {
  if (tvBound()) return false;
  return scanTv();
}

export function paintBindBtns() {
  const native = hasNativeScan();
  const bound = tvBound();
  const scanBtn = $("scanTv");
  if (scanBtn) {
    scanBtn.hidden = !native;
    scanBtn.textContent = bound ? t("phone.room.rebind") : t("phone.room.scan");
  }
  const rebind = $("rebindTv");
  if (rebind) {
    rebind.hidden = !native;
    rebind.textContent = bound ? t("phone.room.rebind") : t("phone.room.bind");
  }
}

export function needTvOrRoom() {
  const code = $("room") ? $("room").value.trim() : "";
  if (!code) {
    openOverlay("roomSheet");
    showToast(t("phone.desk.needRoom"));
    return true;
  }
  return false;
}

export function tvUrl(code) {
  return "/tv.html?room=" + encodeURIComponent(code);
}

export function openTv(code) {
  const url = tvUrl(code);
  $("openTv").href = url;
  window.open(url, "lovktv-tv");
}

function nativeLanHttp() {
  try {
    return typeof window.LovKtvPhone !== "undefined" && typeof window.LovKtvPhone.http === "function";
  } catch (err) {
    return false;
  }
}

function lanReady() {
  if (!lanOrigin()) return true;
  return !!(window.__lovktvLanFetch || window.__lovktvNativeLan);
}

function waitLanReady() {
  if (lanReady() || !nativeLanHttp()) return Promise.resolve();
  return new Promise((resolve) => {
    let n = 0;
    const timer = setInterval(() => {
      n += 1;
      if (lanReady() || n > 20) {
        clearInterval(timer);
        resolve();
      }
    }, 50);
  });
}

export async function joinRoom(openScreen, quiet) {
  let code = $("room").value.trim().toUpperCase();
  $("join").disabled = true;
  try {
    await waitLanReady();
    if (!code) {
      const created = await fetchJson(roomUrl("/api/rooms"), { method: "POST" });
      if (!created.ok || !created.data.code) throw new Error(created.data.detail || t("phone.room.openFail"));
      code = created.data.code;
    }
    $("room").value = code;
    localStorage.setItem("room", code);
    /** @type {{ ok: boolean, data: Room }} */
    const { ok, data: room } = await fetchJson(roomUrl("/api/rooms/" + code));
    if (!ok || !room.code) throw new Error(room.detail || t("phone.room.fail"));
    $("roomState").textContent = t("phone.room.joined", { code: room.code, n: room.queue.length });
    $("openTv").href = tvUrl(room.code);
    paintTopRoom(room.code);
    if (openScreen) {
      $("roomState").textContent = t("phone.room.joinedTv", { code: room.code });
    }
    if (!quiet) {
      closeOverlay("roomSheet");
      showToast(t("phone.room.joinedToast", { code: room.code }));
    }
    await api.loadRoom({ quiet: !!quiet });
  } catch (err) {
    $("roomState").textContent = t("phone.room.fail");
    if (!quiet) showToast(lanOrigin() ? t("phone.room.lanFail") : t("phone.room.fail"));
  }
  $("join").disabled = false;
}

export function bindJoin() {
  paintBindBtns();
  if ($("scanTv")) $("scanTv").onclick = () => scanTv();
  if ($("rebindTv")) $("rebindTv").onclick = () => scanTv();
  $("join").onclick = () => {
    joinRoom(false);
  };
  $("openTv").onclick = (event) => {
    const code = $("room").value.trim().toUpperCase();
    if (!code) return;
    event.preventDefault();
    openTv(code);
  };
  if ($("room").value) {
    $("openTv").href = tvUrl($("room").value);
    joinRoom(false, true);
    return;
  }
  fetchJson(roomUrl("/api/rooms")).then(({ ok, data }) => {
    if (!ok || !data.code || $("room").value) return;
    $("room").value = String(data.code).toUpperCase();
    localStorage.setItem("room", $("room").value);
    $("openTv").href = tvUrl($("room").value);
    joinRoom(false, true);
  });
}

