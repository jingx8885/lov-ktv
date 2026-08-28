import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";

export const WHO_ICO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4 4 0 100-8 4 4 0 000 8zm0 1.8c-4.2 0-7.6 2.1-7.6 4.7V20h15.2v-1.5c0-2.6-3.4-4.7-7.6-4.7z"/></svg>';
export const ROOM_ICO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10.8L12 4l8 6.8V20a1 1 0 01-1 1h-5.2v-6.2H10.2V21H5a1 1 0 01-1-1v-9.2z"/></svg>';
export const ICO = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6.2v11.6L18.8 12z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h5v14H5zm9 0h5v14h-5z"/></svg>',
  listen: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12a7 7 0 0114 0v6a2 2 0 01-2 2h-2v-7h3a6 6 0 00-12 0h3v7H7a2 2 0 01-2-2v-6z"/></svg>',
  plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l1 2h5v2H3V5h5l1-2zm1 6h2v9h-2V9zm4 0h2v9h-2V9zM8 9h2v9H8V9z"/></svg>',
  save: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h12l4 4v14H5V3zm2 2v6h10V5H7zm10 16v-7H7v7h10zM9 6h6v3H9V6z"/></svg>',
  seq: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h10v2H4zm0 5h10v2H4zm0 5h7v2H4zm12.2-1.2L19 18l3.8-3.2-1.2-1.5-1.6 1.3V7h-2v7.6l-1.6-1.3z"/></svg>',
  shuffle: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 3h4v4h-2V6.4l-3.2 3.2-1.4-1.4L17.6 5H17V3zM3 7h6.6l7 7H21v2h-5.6l-7-7H3V7zm14 8.6l3.2 3.2V17h2v4h-4v-2h1.6L14.6 15l1.4-1.4 1 1zM3 15h4.6l2.2-2.2 1.4 1.4L8.4 17H3v-2z"/></svg>',
};

export function songInitial(text) {
  const ch = String(text || "").replace(/[^\p{L}\p{N}]/gu, "")[0];
  return ch || "♪";
}

export function songLetter(text) {
  const folded = String(text || "").normalize("NFKC");
  for (const ch of folded) {
    if (/[A-Za-z]/.test(ch)) return ch.toUpperCase();
    if (/[0-9]/.test(ch)) return "#";
  }
  return "#";
}

export function paintTopRoom(code) {
  const text = String(code || $("room").value || "进房").trim().slice(0, 8) || "进房";
  $("topRoom").innerHTML = `${ROOM_ICO}<span>${text}</span>`;
}

export function paintTopWho(user) {
  if (user && user.avatar) {
    $("topWho").innerHTML = `<img alt="" src="${user.avatar}">`;
    return;
  }
  const mark = user ? String(user.sid || user.nickname || "").slice(0, 1) : "";
  $("topWho").innerHTML = mark ? `<em>${mark}</em>` : WHO_ICO;
}

api.paintTopRoom = paintTopRoom;
api.paintTopWho = paintTopWho;
api.ICO = ICO;
