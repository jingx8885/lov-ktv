import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { lanOrigin, roomUrl } from "../../origin.js?v=scan1";
import { t } from "../../../shared/i18n/js/i18n.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { ICO, songInitial, paintTopRoom } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { showDeskPane } from "./library.js";

let lastLanFailAt = 0;

export async function loadRoom() {
  const code = $("room").value.trim();
  if (!code) {
    if ($("nowCard") && !$("nowCard").innerHTML.trim()) {
      $("nowCard").innerHTML = `<div class="now-idle"><span class="now-cover">${ICO.listen}</span><div><b>${t("phone.desk.idle")}</b><p class="tiny">${t("phone.desk.idleHint")}</p></div></div>`;
    }
    return;
  }
  /** @type {{ ok: boolean, data: Room }} */
  const { ok, data: room } = await fetchJson(roomUrl(`/api/rooms/${code}`)).catch(() => ({ ok: false, data: {} }));
  if (!ok || !room.code) {
    if (lanOrigin() && Date.now() - lastLanFailAt > 8000) {
      lastLanFailAt = Date.now();
      showToast(t("phone.room.lanFail"));
    }
    return;
  }
  $("roomState").textContent = t("phone.room.stat", { code: room.code, n: room.queue.length });
  paintTopRoom(room.code);
  const now = room.now_playing;
  const mix = room.vocal_mix || 0;
  api.paintVocalMix(mix);
  api.paintMix(room);
  api.connectRoomRtc(code);
  if ($("queueCount")) $("queueCount").textContent = room.queue.length ? String(room.queue.length) : "";
  $("nowCard").innerHTML = now
    ? `<button type="button" class="now-hit" id="nowToPlayer" ${now.status === "ready" ? "" : "disabled"}>
            <span class="now-cover">${now.status === "ready" ? ICO.play : escapeHtml(songInitial(now.title))}</span>
            <div>
              <p class="kicker">${now.status === "ready" ? t("phone.desk.now") : (STATUS[now.status] || now.status)}</p>
              <b>${escapeHtml(now.title)}</b>
              <p class="tiny">${escapeHtml(now.artist || "")}</p>
            </div>
            ${now.status === "ready" ? `<span class="now-go">${ICO.play}</span>` : ""}
          </button>`
    : `<div class="now-idle">
            <span class="now-cover">${ICO.listen}</span>
            <div><b>${t("phone.desk.idle")}</b><p class="tiny">${t("phone.desk.idleHint")}</p></div>
          </div>`;
  const toPlayer = $("nowToPlayer");
  if (toPlayer && now && now.status === "ready") toPlayer.onclick = () => api.openPlayer(now.song_id);
  $("queue").innerHTML = room.queue.map((item, i) => {
    const playing = i === room.now_index;
    const ready = item.status === "ready";
    return `
        <div class="desk-row ${playing ? "on" : ""}">
          <span class="desk-index ${playing ? "live" : ""}">${playing ? ICO.play : String(i + 1)}</span>
          <div class="desk-copy">
            <b>${escapeHtml(item.title)}</b>
            <span class="tiny">${playing ? t("phone.desk.now") : (ready ? t("phone.desk.nextQueued") : (STATUS[item.status] || item.status))}</span>
          </div>
          <div class="desk-actions">
            <button class="row-action ${playing ? "on" : "ghost"}" data-play="${item.id}" aria-label="${t("phone.desk.playThis")}">${ICO.play}</button>
          </div>
        </div>`;
  }).join("") || `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.desk.emptyQueue")}</p><button class="btn primary" type="button" data-go-lib>${t("phone.desk.goLib")}</button></div>`;
  $("queue").querySelectorAll("[data-play]").forEach((btn) => {
    btn.onclick = async () => {
      const { ok, data } = await fetchJson(roomUrl(`/api/rooms/${code}/play`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: btn.dataset.play }),
      });
      if (!ok) showToast(data.detail || t("phone.desk.cantQueue"));
      loadRoom();
    };
  });
  const goLib = $("queue").querySelector("[data-go-lib]");
  if (goLib) goLib.onclick = () => showDeskPane("lib");
}

