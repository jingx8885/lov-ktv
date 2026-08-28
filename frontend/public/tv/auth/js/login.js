import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
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
    const { data } = await fetchJson("/api/host");
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
  const { data } = await fetchJson("/api/auth/me", { credentials: "same-origin" }).catch(() => ({ data: { user: null } }));
  return data.user;
}

export async function pollLogin() {
  if (!state.loginTicket) return;
  const { ok, data } = await fetchJson("/api/auth/qr/" + state.loginTicket + "?claim=1", { credentials: "same-origin" });
  if (!ok) return;
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
  const { data } = await fetchJson("/api/auth/qr", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room: state.room ? state.room.code : roomCode() }),
  });
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
  /** @type {{ data: Room }} */
  const roomRes = wanted
    ? await fetchJson("/api/rooms/" + wanted)
    : await fetchJson("/api/rooms", { method: "POST" });
  state.room = roomRes.data;
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

