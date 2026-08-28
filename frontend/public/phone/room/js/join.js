import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { api } from "../../api.js";
import { paintTopRoom } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { closeOverlay } from "../../ui/js/overlays.js";

export function tvUrl(code) {
  return "/tv.html?room=" + encodeURIComponent(code);
}

export function openTv(code) {
  const url = tvUrl(code);
  $("openTv").href = url;
  window.open(url, "lovktv-tv");
}

export async function joinRoom(openScreen, quiet) {
  let code = $("room").value.trim().toUpperCase();
  $("join").disabled = true;
  try {
    if (!code) {
      const created = await fetchJson("/api/rooms", { method: "POST" });
      if (!created.ok || !created.data.code) throw new Error(created.data.detail || t("phone.room.openFail"));
      code = created.data.code;
    }
    $("room").value = code;
    localStorage.setItem("room", code);
    /** @type {{ ok: boolean, data: Room }} */
    const { ok, data: room } = await fetchJson("/api/rooms/" + code);
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
    await api.loadRoom();
  } catch (err) {
    $("roomState").textContent = t("phone.room.fail");
    if (!quiet) showToast(t("phone.room.fail"));
  }
  $("join").disabled = false;
}

export function bindJoin() {
  $("join").onclick = () => joinRoom(false);
  $("openTv").onclick = (event) => {
    const code = $("room").value.trim().toUpperCase();
    if (!code) return;
    event.preventDefault();
    openTv(code);
  };
  if ($("room").value) {
    $("openTv").href = tvUrl($("room").value);
    joinRoom(false, true);
  }
}

