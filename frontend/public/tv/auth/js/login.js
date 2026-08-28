import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { state } from "../../state.js";

export function renderQr(url, target) {
  const box = $(target || "qr");
  box.innerHTML = "";
  if (typeof qrcode === "function") {
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    box.innerHTML = qr.createSvgTag(5, 0);
    return;
  }
  box.textContent = url;
}

export function roomCode() {
  return (new URLSearchParams(location.search).get("room") || localStorage.getItem("tvRoom") || "").toUpperCase();
}

export async function hostOrigin() {
  try {
    const data = await fetch("/api/host").then((r) => r.json());
    if (data && data.origin) return String(data.origin).replace(/\/$/, "");
  } catch (err) {}
  return location.origin;
}

export function renderUserChip(user) {
  $("tvUser").textContent = user ? (user.sid || user.nickname || "已登录") : "未登录";
  $("tvLoginBtn").textContent = user ? "换账号" : "登录";
  if (user && user.avatar) {
    $("tvAvatar").hidden = false;
    $("tvAvatar").src = user.avatar;
  } else {
    $("tvAvatar").hidden = true;
  }
}

export async function currentUser() {
  const data = await fetch("/api/auth/me", { credentials: "same-origin" }).then((r) => r.json()).catch(() => ({ user: null }));
  return data.user;
}

export async function pollLogin() {
  if (!state.loginTicket) return;
  const res = await fetch("/api/auth/qr/" + state.loginTicket + "?claim=1", { credentials: "same-origin" });
  if (!res.ok) return;
  const data = await res.json();
  if (data.status === "expired") {
    $("loginHint").textContent = "二维码过期了，点刷新";
    return;
  }
  if (data.status === "ok" && data.user) {
    clearInterval(state.loginTimer);
    state.loginTicket = "";
    $("loginGate").hidden = true;
    renderUserChip(data.user);
  }
}

export async function startLoginQr() {
  $("loginGate").hidden = false;
  $("loginHint").textContent = "正在生成二维码…";
  const res = await fetch("/api/auth/qr", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room: state.room ? state.room.code : roomCode() }),
  });
  const data = await res.json();
  state.loginTicket = data.ticket;
  renderQr(data.url, "loginQr");
  $("loginHint").textContent = "微信扫一下就行，约 3 分钟有效";
  if (state.loginTimer) clearInterval(state.loginTimer);
  state.loginTimer = setInterval(pollLogin, 2000);
}

export async function bootAuth() {
  if (/LovKtvAndroidTV/i.test(navigator.userAgent || "") || new URLSearchParams(location.search).get("androidtv")) {
    document.body.classList.add("androidtv");
  }
  const wanted = roomCode();
  state.room = wanted
    ? await fetch("/api/rooms/" + wanted).then((r) => r.json())
    : await fetch("/api/rooms", { method: "POST" }).then((r) => r.json());
  localStorage.setItem("tvRoom", state.room.code);
  $("code").textContent = state.room.code;
  const url = (await hostOrigin()) + "/m.html?room=" + state.room.code + "&v=queue3";
  $("phoneLink").href = url;
  renderQr(url);
  const user = await currentUser();
  renderUserChip(user);
  sessionStorage.setItem("tvSkipLogin", "1");
  $("loginGate").hidden = true;
  $("tvLoginBtn").onclick = () => startLoginQr();
  $("refreshLogin").onclick = () => startLoginQr();
  $("skipLogin").onclick = () => {
    sessionStorage.setItem("tvSkipLogin", "1");
    $("loginGate").hidden = true;
    if (state.loginTimer) clearInterval(state.loginTimer);
  };
}

api.roomCode = roomCode;
api.hostOrigin = hostOrigin;
