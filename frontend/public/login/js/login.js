import { t, bootI18n, onLangChange, applyDom } from "../../shared/i18n/js/i18n.js";
import { $ } from "../../shared/ui/js/dom.js";
import { fetchJson } from "../../shared/ui/js/http.js";
import { isAccount, submitAccount } from "../../shared/ui/js/account.js";

bootI18n();

const params = new URLSearchParams(location.search);
const ticket = params.get("login") || params.get("ticket") || "";
const room = (params.get("room") || "").toUpperCase();
const next = params.get("next") || "";
const inWechat = /MicroMessenger/i.test(navigator.userAgent || "");
const deviceKey = "lovktv_device";

let meUser = null;
let meQuota = null;
let scanLead = false;
let errorRaw = "";
let authMode = "login";

function deviceId() {
  let id = localStorage.getItem(deviceKey);
  if (!id) {
    id =
      (crypto.randomUUID && crypto.randomUUID().replace(/-/g, "")) ||
      String(Date.now()) + Math.random().toString(16).slice(2);
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

function resolveError(raw) {
  if (!raw) return "";
  const translated = t(raw);
  if (translated !== raw) return translated;
  return raw;
}

function showError(text) {
  $("err").hidden = !text;
  $("err").textContent = text || "";
}

function signedIn() {
  return isAccount(meUser);
}

function paintQuota() {
  const hint = $("quotaHint");
  if (!hint) return;
  const limit = (meQuota && meQuota.limit) || 5;
  const remaining = meQuota && typeof meQuota.remaining === "number" ? meQuota.remaining : limit;
  hint.hidden = signedIn();
  hint.textContent = signedIn() ? "" : t("login.quota", { n: remaining });
}

function paintLead() {
  if (signedIn()) {
    $("heading").textContent = t("login.done");
    $("lead").textContent = ticket ? t("login.doneTv") : t("login.doneId");
    if (meUser.wechat) $("meHint").textContent = t("login.wechatLock");
    else if (meUser.username) $("meHint").textContent = meUser.username;
    else $("meHint").textContent = t("login.deviceId");
    return;
  }
  $("heading").textContent = t("login.heading");
  $("panelKicker").textContent = t(authMode === "register" ? "login.registerKicker" : "login.panelKicker");
  $("lead").textContent = scanLead ? t("login.leadScan") : t(authMode === "register" ? "login.registerLead" : "login.lead");
  paintQuota();
}

function setAuthMode(mode) {
  authMode = mode === "register" ? "register" : "login";
  const register = authMode === "register";
  $("authMode").value = authMode;
  $("authLoginTab").classList.toggle("active", !register);
  $("authRegisterTab").classList.toggle("active", register);
  $("authLoginTab").setAttribute("aria-selected", String(!register));
  $("authRegisterTab").setAttribute("aria-selected", String(register));
  $("passRegister").innerHTML = register
    ? `<span data-i18n="login.hasAccount">已有账号？</span> <span class="switch-link" data-i18n="login.loginNow">立即登录</span>`
    : `<span data-i18n="login.noAccount">还没有账号？</span> <span class="switch-link" data-i18n="login.register">立即注册</span>`;
  $("password").setAttribute("autocomplete", register ? "new-password" : "current-password");
  applyDom($("passBox"));
  $("passLogin").textContent = t(register ? "login.registerAction" : "login.enter");
  paintLead();
}

function renderUser(user, quota) {
  meUser = user;
  if (quota) meQuota = quota;
  const inAccount = signedIn();
  $("meBox").hidden = !inAccount;
  $("passBox").hidden = inAccount;
  $("loginBox").hidden = inAccount;
  if (!inAccount) {
    paintLead();
    return;
  }
  $("sid").textContent = user.username || user.sid || (user.id || "").slice(0, 6).toUpperCase();
  paintLead();
}

async function loadMe() {
  const { data } = await fetchJson("/api/auth/me", { credentials: "same-origin" });
  meQuota = data.quota || meQuota;
  return data.user;
}

async function confirmTicket() {
  if (!ticket) return true;
  const { ok, data } = await fetchJson("/api/auth/qr/" + ticket + "/confirm", {
    method: "POST",
    credentials: "same-origin"
  });
  if (ok) return true;
  showError(data.detail || t("login.qrExpired"));
  return false;
}

async function deviceLogin() {
  const { ok, data } = await fetchJson("/api/auth/device", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId() })
  });
  if (!ok) {
    showError(data.detail || t("login.deviceFail"));
    return null;
  }
  return data.user;
}

async function finishAccount(user) {
  if (!user) return;
  await confirmTicket();
  renderUser(user);
  if (next && next.startsWith("/") && !ticket) location.replace(next);
}

async function runPass(mode) {
  showError("");
  const username = $("username").value.trim();
  const password = $("password").value;
  if (!username) {
    showError(t("login.needName"));
    $("username").focus();
    return;
  }
  if (!password) {
    showError(t("login.needPass"));
    $("password").focus();
    return;
  }
  const { ok, data } = await submitAccount(mode, username, password);
  if (!ok) {
    showError(data.detail || t("login.deviceFail"));
    return;
  }
  if (data.quota) meQuota = data.quota;
  await finishAccount(data.user);
}

onLangChange(() => {
  applyDom();
  paintLead();
  if (signedIn()) {
    $("sid").textContent = meUser.username || meUser.sid || (meUser.id || "").slice(0, 6).toUpperCase();
  }
  if (errorRaw) showError(resolveError(errorRaw));
});

$("logout").onclick = async () => {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  renderUser(null, meQuota);
  $("passBox").hidden = false;
  $("loginBox").hidden = false;
  setAuthMode("login");
  paintLead();
};

$("deviceLogin").onclick = async () => {
  showError("");
  const user = await deviceLogin();
  if (!user) return;
  await finishAccount(user);
};

$("passBox").addEventListener("submit", (event) => {
  event.preventDefault();
  runPass(authMode);
});
$("authLoginTab").onclick = () => setAuthMode("login");
$("authRegisterTab").onclick = () => setAuthMode("register");
$("passRegister").onclick = () => setAuthMode(authMode === "register" ? "login" : "register");
$("togglePassword").onclick = () => {
  const input = $("password");
  const visible = input.type === "text";
  input.type = visible ? "password" : "text";
  $("togglePassword").textContent = t(visible ? "login.showPassword" : "login.hidePassword");
  $("togglePassword").setAttribute("aria-label", t(visible ? "login.showPassword" : "login.hidePassword"));
};

(async function boot() {
  errorRaw = params.get("error") || "";
  if (errorRaw) showError(resolveError(errorRaw));
  $("wechatScan").href = scanHref();
  if (room) {
    $("toTv").href = "/tv.html?room=" + room;
    $("toMobile").href = "/m.html?room=" + room;
    if (!$("username").value) $("username").value = room;
  }
  const statusHit = await fetchJson("/api/auth/status").catch(() => ({ data: {} }));
  const status = statusHit.data;
  const wechatOn = !!(status.wechat || status.wechat_quick);
  if (status.guest_limit && !meQuota) {
    meQuota = { limit: status.guest_limit, remaining: status.guest_limit, unlimited: false };
  }
  const user = await loadMe();
  if (!params.get("error") && !isAccount(user) && inWechat && wechatOn && ticket) {
    location.replace(scanHref());
    return;
  }
  if (isAccount(user)) {
    await confirmTicket();
    renderUser(user);
    if (next && next.startsWith("/") && !ticket && params.get("ok") !== "1") location.replace(next);
    return;
  }
  $("passBox").hidden = false;
  $("loginBox").hidden = false;
  setAuthMode("login");
  $("deviceLogin").hidden = wechatOn;
  if (wechatOn && !inWechat && ticket) {
    scanLead = true;
    $("lead").textContent = t("login.leadScan");
  }
  paintQuota();
})();
