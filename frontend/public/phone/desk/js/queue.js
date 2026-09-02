import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { adoptLan, lanOrigin, roomUrl } from "../../origin.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { ICO, paintTopRoom } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { showDeskPane } from "./library.js";
import { songArtist, songTitle } from "../../../shared/ui/js/song.js";
import { fetchRoom, roomStamp } from "../../room/js/room/state.js";

let lastLanFailAt = 0;
let lastRoomStamp = "";

export async function loadRoom(opts) {
  const quiet = !!(opts && opts.quiet);
  const injected = opts && opts.room;
  const code = $("room").value.trim();
  if (!code) {
    if ($("nowBar")) $("nowBar").classList.add("is-idle");
    if ($("nowCard") && !$("nowCard").innerHTML.trim()) {
      $("nowCard").innerHTML =
        `<div class="now-idle"><span class="now-cover">${ICO.listen}</span><div><b>${t("phone.desk.idle")}</b><p class="tiny">${t("phone.desk.idleHint")}</p></div></div>`;
    }
    return;
  }
  let ok = true;
  /** @type {Room | null} */
  let room = injected && injected.code ? injected : null;
  if (!room) {
    ({ ok, data: room } = await fetchRoom(code));
    if ((!ok || !room.code) && lanOrigin()) {
      for (let i = 0; i < 3 && (!ok || !room.code); i++) {
        await new Promise((resolve) => {
          setTimeout(resolve, 200);
        });
        ({ ok, data: room } = await fetchRoom(code));
      }
    }
  } else {
    ok = true;
  }
  if (!ok || !room || !room.code) {
    if (lanOrigin()) {
      const cloud = await fetchJson("/api/rooms/" + code).catch(() => ({ ok: false, data: {} }));
      if (cloud.ok && cloud.data && cloud.data.code && adoptLan(cloud.data)) return;
    }
    if (!quiet && lanOrigin() && Date.now() - lastLanFailAt > 8000) {
      lastLanFailAt = Date.now();
      showToast(t("phone.room.lanFail"));
    }
    return;
  }
  if (adoptLan(room)) return;
  const stamp = roomStamp(room);
  if (quiet && stamp === lastRoomStamp && $("queue").querySelector(".desk-row, .empty-state")) return;
  lastRoomStamp = stamp;
  $("roomState").textContent = t("phone.room.stat", { code: room.code, n: room.queue.length });
  paintTopRoom(room.code);
  const now = room.now_playing;
  const mix = room.vocal_mix || 0;
  api.paintVocalMix(mix);
  api.paintMix(room);
  api.connectRoomRtc(code);
  if ($("queueCount")) $("queueCount").textContent = room.queue.length ? String(room.queue.length) : "";
  if ($("nowBar")) $("nowBar").classList.toggle("is-idle", !now);
  $("nowCard").innerHTML = now
    ? `<div class="now-hit">
            <span class="now-cover">${now.status === "ready" ? ICO.play : ICO.note}</span>
            <div>
              <p class="kicker">${now.status === "ready" ? t("phone.desk.now") : STATUS[now.status] || now.status}</p>
              <b>${escapeHtml(songTitle(now))}</b>
              <p class="tiny">${escapeHtml(songArtist(now))}</p>
            </div>
          </div>`
    : `<div class="now-idle">
            <span class="now-cover">${ICO.listen}</span>
            <div><b>${t("phone.desk.idle")}</b><p class="tiny">${t("phone.desk.idleHint")}</p></div>
          </div>`;
  $("queue").innerHTML =
    room.queue
      .map((item, i) => {
        const playing = i === room.now_index;
        const ready = item.status === "ready";
        const canBump = !playing && i > (room.now_index || 0) + 1;
        return `
        <div class="desk-row ${playing ? "on" : ""}">
          <span class="desk-index ${playing ? "live" : ""}">${playing ? ICO.play : String(i + 1)}</span>
          <div class="desk-copy">
            <b>${escapeHtml(songTitle(item))}</b>
            <span class="tiny">${playing ? t("phone.desk.now") : ready ? t("phone.desk.nextQueued") : STATUS[item.status] || item.status}</span>
          </div>
          <div class="desk-actions">
            ${canBump ? `<button class="row-action ghost" data-bump="${item.id}" aria-label="${t("phone.desk.bump")}">${ICO.bump}</button>` : ""}
            <button class="row-action ${playing ? "on" : "ghost"}" data-play="${item.id}" aria-label="${t("phone.desk.playThis")}">${ICO.play}</button>
          </div>
        </div>`;
      })
      .join("") ||
    `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.desk.emptyQueue")}</p><button class="btn primary" type="button" data-go-lib>${t("phone.desk.goLib")}</button></div>`;
  $("queue")
    .querySelectorAll("[data-play]")
    .forEach((btn) => {
      btn.onclick = async () => {
        const { ok, data } = await fetchJson(roomUrl(`/api/rooms/${code}/play`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: btn.dataset.play })
        });
        if (!ok) showToast(data.detail || t("phone.desk.cantQueue"));
        loadRoom({ room: data });
      };
    });
  $("queue")
    .querySelectorAll("[data-bump]")
    .forEach((btn) => {
      btn.onclick = async () => {
        const { ok, data } = await fetchJson(roomUrl(`/api/rooms/${code}/bump`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: btn.dataset.bump })
        });
        if (!ok) showToast(data.detail || t("phone.desk.cantQueue"));
        else showToast(t("phone.desk.bumped"));
        loadRoom({ room: data });
      };
    });
  const goLib = $("queue").querySelector("[data-go-lib]");
  if (goLib) goLib.onclick = () => showDeskPane("lib");
}
