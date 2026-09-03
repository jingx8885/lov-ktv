import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { isAccount, submitAccount } from "../../../shared/ui/js/account.js";
import { paintTopWho } from "./icons.js";
import { showToast } from "./toast.js";
import { openOverlay } from "./overlays.js";
import { state } from "../../state.js";

let lastQuota = null;

export function loginQs() {
  const q = new URLSearchParams();
  if ($("room").value) q.set("room", $("room").value.trim().toUpperCase());
  q.set("next", location.pathname + location.search);
  return "/api/auth/scan?" + q.toString();
}

function fillUsername() {
  const input = $("whoUsername");
  if (!input || input.value.trim()) return;
  const room = ($("room").value || "").trim().toUpperCase();
  if (room) input.value = room;
}

function paintQuotaBar(quota, signedIn) {
  lastQuota = quota || lastQuota;
  const bar = $("quotaBar");
  const whoQuota = $("whoQuota");
  if (signedIn || !lastQuota || lastQuota.unlimited) {
    if (bar) bar.hidden = true;
    if (whoQuota) whoQuota.hidden = true;
    return;
  }
  const remaining = typeof lastQuota.remaining === "number" ? lastQuota.remaining : lastQuota.limit || 5;
  if (bar) {
    bar.hidden = false;
    if (remaining <= 0) {
      bar.innerHTML = `${t("phone.search.quotaOut")} <button type="button" id="quotaLogin">${t("phone.search.quotaLogin")}</button>`;
    } else {
      bar.innerHTML = `${t("phone.search.quota", { n: remaining })} <button type="button" id="quotaLogin">${t("phone.search.quotaLogin")}</button>`;
    }
    const btn = $("quotaLogin");
    if (btn) btn.onclick = () => openOverlay("whoSheet");
  }
  if (whoQuota) {
    whoQuota.hidden = false;
    whoQuota.textContent = remaining <= 0 ? t("phone.search.quotaOut") : t("phone.search.quota", { n: remaining });
  }
}

function showWhoError(text) {
  const el = $("whoErr");
  if (!el) return;
  el.hidden = !text;
  el.textContent = text || "";
}

export async function loadWho() {
  const { data } = await fetchJson("/api/auth/me", { credentials: "same-origin" }).catch(() => ({
    data: { user: null }
  }));
  const user = data.user;
  state.songAdmin = !!(data.user && data.user.admin) || !!data.song_admin;
  document.dispatchEvent(new CustomEvent("lovktv-auth-change"));
  const signed = isAccount(user);
  const deskCta = $("deskLoginCta");
  if (deskCta) {
    deskCta.hidden = signed;
    deskCta.onclick = () => openOverlay("whoSheet");
  }
  fillUsername();
  $("whoName").textContent = signed
    ? user.username || user.sid || user.nickname || t("phone.who.in")
    : t("phone.who.out");
  $("whoHint").textContent = signed
    ? user.wechat
      ? t("phone.who.wechat")
      : t("phone.who.account", { name: user.username || user.sid || "" })
    : t("phone.who.hint");
  $("whoPassForm").hidden = signed;
  $("whoLogin").hidden = signed;
  $("whoLogin").href = loginQs();
  $("whoLogout").hidden = !signed;
  paintQuotaBar(data.quota, signed);
  const pointsEl = $("whoPoints");
  if (pointsEl) {
    const n = data.points && typeof data.points.balance === "number" ? data.points.balance : 0;
    pointsEl.hidden = false;
    pointsEl.textContent = t("phone.who.points", { n });
  }
  if (signed && user.avatar) {
    $("whoAvatar").hidden = false;
    $("whoAvatar").src = user.avatar;
    $("topWho").innerHTML = `<img alt="" src="${user.avatar}">`;
  } else {
    $("whoAvatar").hidden = true;
    paintTopWho(signed ? user : null);
  }
}

async function runWhoPass(mode) {
  fillUsername();
  showWhoError("");
  const username = $("whoUsername").value.trim();
  const password = $("whoPassword").value;
  if (!username) {
    showWhoError(t("login.needName"));
    $("whoUsername").focus();
    return;
  }
  if (!password) {
    showWhoError(t("login.needPass"));
    $("whoPassword").focus();
    return;
  }
  const { ok, data } = await submitAccount(mode, username, password);
  if (!ok) {
    showWhoError(data.detail || t("login.deviceFail"));
    return;
  }
  $("whoPassword").value = "";
  await loadWho();
  showToast(t("login.done"));
}

export function bindWho() {
  const tabWho = $("tabWho");
  if (tabWho) tabWho.onclick = () => {
    tabWho.classList.add("on");
    openOverlay("whoSheet");
    fillUsername();
  };
  $("whoLogout").onclick = async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    await loadWho();
    showToast(t("phone.who.bye"));
  };
  $("whoPassForm").addEventListener("submit", (event) => {
    event.preventDefault();
    runWhoPass("login");
  });
  $("whoRegister").onclick = () => runWhoPass("register");
  loadWho();
}

export function promptLogin() {
  openOverlay("whoSheet");
  fillUsername();
  $("whoUsername").focus();
}
