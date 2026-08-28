import { $ } from "../../shared/ui/js/dom.js";

const params = new URLSearchParams(location.search);
const ticket = params.get("login") || params.get("ticket") || "";
const room = (params.get("room") || "").toUpperCase();
const next = params.get("next") || "";
const inWechat = /MicroMessenger/i.test(navigator.userAgent || "");
const deviceKey = "lovktv_device";

function deviceId() {
  let id = localStorage.getItem(deviceKey);
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID().replace(/-/g, "")) || String(Date.now()) + Math.random().toString(16).slice(2);
    localStorage.setItem(deviceKey, id);
  }
  return id;
}

function scanHref() {
  const q = new URLSearchParams();
  if (ticket) q.set("ticket", ticket);
  if (room) q.set("room", room);
  if (next) q.set("next", next);
  const qs = q.toString();
  return "/api/auth/scan" + (qs ? "?" + qs : "");
}

function showError(text) {
  $("err").hidden = !text;
  $("err").textContent = text || "";
}

function renderUser(user) {
  $("meBox").hidden = !user;
  $("loginBox").hidden = !!user;
  if (!user) return;
  $("sid").textContent = user.sid || (user.id || "").slice(0, 6).toUpperCase();
  $("heading").textContent = "已认号";
  $("lead").textContent = ticket ? "电视马上会进。这个 ID 下次扫还是你。" : "这个 ID 下次扫还是你。";
  $("meHint").textContent = user.wechat ? "微信 openid 锁定" : "本机身份";
}

async function loadMe() {
  const data = await fetch("/api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
  return data.user;
}

async function confirmTicket() {
  if (!ticket) return true;
  const res = await fetch("/api/auth/qr/" + ticket + "/confirm", { method: "POST", credentials: "same-origin" });
  if (res.ok) return true;
  const data = await res.json().catch(() => ({}));
  showError(data.detail || "电视码过期了，请刷新电视再扫");
  return false;
}

async function deviceLogin() {
  const res = await fetch("/api/auth/device", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId() }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    showError(data.detail || "本机认号失败");
    return null;
  }
  return data.user;
}

$("logout").onclick = async () => {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  renderUser(null);
  $("loginBox").hidden = false;
  $("heading").textContent = "认号";
  $("lead").textContent = "微信扫一下，直接拿一个稳定 ID。";
};

$("deviceLogin").onclick = async () => {
  showError("");
  const user = await deviceLogin();
  if (!user) return;
  await confirmTicket();
  renderUser(user);
  if (next && next.startsWith("/") && !ticket) location.replace(next);
};

(async function boot() {
  if (params.get("error")) showError(params.get("error"));
  $("wechatScan").href = scanHref();
  if (room) {
    $("toTv").href = "/tv.html?room=" + room;
    $("toMobile").href = "/m.html?room=" + room;
  }
  const status = await fetch("/api/auth/status").then((r) => r.json()).catch(() => ({}));
  const wechatOn = !!(status.wechat || status.wechat_quick);
  const user = await loadMe();
  if (!params.get("error") && !user && inWechat && wechatOn) {
    location.replace(scanHref());
    return;
  }
  if (!user && !wechatOn && !params.get("error")) {
    const created = await deviceLogin();
    if (created) {
      await confirmTicket();
      renderUser(created);
      if (next && next.startsWith("/") && !ticket) location.replace(next);
      return;
    }
  }
  if (user) {
    await confirmTicket();
    renderUser(user);
    if (next && next.startsWith("/") && !ticket && params.get("ok") !== "1") location.replace(next);
    return;
  }
  $("loginBox").hidden = false;
  $("deviceLogin").hidden = wechatOn;
  if (wechatOn && !inWechat) {
    $("lead").textContent = "请用微信扫电视上的码，扫完就认号。";
  }
})();
