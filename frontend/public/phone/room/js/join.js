import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
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
      code = created.data.code;
    }
    $("room").value = code;
    localStorage.setItem("room", code);
    /** @type {{ data: Room }} */
    const { data: room } = await fetchJson("/api/rooms/" + code);
    $("roomState").textContent = `已进房 ${room.code} · 队列 ${room.queue.length}`;
    $("openTv").href = tvUrl(room.code);
    paintTopRoom(room.code);
    if (openScreen) {
      $("roomState").textContent = `已进房 ${room.code} · 点「打开电视」看大屏`;
    }
    if (!quiet) {
      closeOverlay("roomSheet");
      showToast(`已进房 ${room.code}`);
    }
    await api.loadRoom();
  } catch (err) {
    $("roomState").textContent = "进房失败，检查服务是否已开";
    if (!quiet) showToast("进房失败，检查服务是否已开");
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

