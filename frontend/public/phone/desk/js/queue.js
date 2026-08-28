import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { STATUS } from "../../../shared/ui/js/status.js";
import { api } from "../../api.js";
import { ICO, songInitial, paintTopRoom } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { showDeskPane } from "./library.js";

export async function loadRoom() {
  const code = $("room").value.trim();
  if (!code) {
    if ($("nowCard") && !$("nowCard").innerHTML.trim()) {
      $("nowCard").innerHTML = `<div class="now-idle"><span class="now-cover">${ICO.listen}</span><div><b>还没在唱</b><p class="tiny">从曲库点一首</p></div></div>`;
    }
    return;
  }
  /** @type {Room} */
  const room = await fetch(`/api/rooms/${code}`).then((r) => r.json());
  $("roomState").textContent = `房间 ${room.code} · 已点 ${room.queue.length}`;
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
              <p class="kicker">${now.status === "ready" ? "正在唱" : (STATUS[now.status] || now.status)}</p>
              <b>${escapeHtml(now.title)}</b>
              <p class="tiny">${escapeHtml(now.artist || "")}</p>
            </div>
            ${now.status === "ready" ? `<span class="now-go">${ICO.play}</span>` : ""}
          </button>`
    : `<div class="now-idle">
            <span class="now-cover">${ICO.listen}</span>
            <div><b>还没在唱</b><p class="tiny">从曲库点一首</p></div>
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
            <span class="tiny">${playing ? "正在唱" : (ready ? "下一首排队" : (STATUS[item.status] || item.status))}</span>
          </div>
          <div class="desk-actions">
            <button class="row-action ${playing ? "on" : "ghost"}" data-play="${item.id}" aria-label="唱这首">${ICO.play}</button>
          </div>
        </div>`;
  }).join("") || `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>还没点歌</p><button class="btn primary" type="button" data-go-lib>去曲库加点</button></div>`;
  $("queue").querySelectorAll("[data-play]").forEach((btn) => {
    btn.onclick = async () => {
      const res = await fetch(`/api/rooms/${code}/play`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: btn.dataset.play }),
      });
      const data = await res.json();
      if (!res.ok) showToast(data.detail || "还不能点这首");
      loadRoom();
    };
  });
  const goLib = $("queue").querySelector("[data-go-lib]");
  if (goLib) goLib.onclick = () => showDeskPane("lib");
}

api.loadRoom = loadRoom;
