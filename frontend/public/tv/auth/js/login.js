import { t } from "../../../shared/i18n/js/i18n.js";
import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { state } from "../../state.js";

let lastUser = null;
let lastHintKey = "tv.loginHint";

function setLoginHint(key) {
  lastHintKey = key;
  $("loginHint").textContent = t(key);
}

export function renderQr(url, target) {
  const box = $(target || "qr");
  box.innerHTML = "";
  if (typeof qrcode === "function") {
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    if (document.body.classList.contains("androidtv") && typeof qr.createImgTag === "function") {
      box.innerHTML = qr.createImgTag(5, 0);
      return;
    }
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
    const process = data && data.process_origin ? String(data.process_origin).replace(/\/$/, "") : "";
    if (process) return process;
    if (data && data.origin) return String(data.origin).replace(/\/$/, "");
  } catch (err) {}
  return location.origin;
}

export function renderUserChip(user) {
  if (user !== undefined) lastUser = user;
  const who = lastUser;
  $("tvUser").textContent = who ? (who.sid || who.nickname || t("tv.in")) : t("tv.out");
  $("tvLoginBtn").textContent = who ? t("tv.switch") : t("tv.login");
  if (who && who.avatar) {
    $("tvAvatar").hidden = false;
    $("tvAvatar").src = who.avatar;
  } else {
    $("tvAvatar").hidden = true;
  }
  if ($("loginHint")) $("loginHint").textContent = t(lastHintKey);
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
    setLoginHint("tv.loginHintExp");
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
  setLoginHint("tv.loginHintWait");
  const { data } = await fetchJson("/api/auth/qr", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room: state.room ? state.room.code : roomCode() }),
  });
  state.loginTicket = data.ticket;
  renderQr(data.url, "loginQr");
  setLoginHint("tv.loginHintOk");
  if (state.loginTimer) clearInterval(state.loginTimer);
  state.loginTimer = setInterval(pollLogin, 2000);
}

export async function bootAuth() {
  if (/LovKtvAndroidTV/i.test(navigator.userAgent || "") || new URLSearchParams(location.search).get("androidtv")) {
    document.body.classList.add("androidtv");
  }
  const wanted = roomCode();
  /** @type {{ ok: boolean, data: Room }} */
  const roomRes = wanted
    ? await fetchJson("/api/rooms/" + wanted)
    : await fetchJson("/api/rooms", { method: "POST" });
  if (!roomRes.ok || !roomRes.data || !roomRes.data.code) {
    throw new Error((roomRes.data && roomRes.data.detail) || t("tv.openFail"));
  }
  localStorage.setItem("tvRoom", state.room.code);
  $("code").textContent = state.room.code;
  let process = "";
  let lan = "";
  try {
    const { data } = await fetchJson("/api/host");
    process = data && data.process_origin ? String(data.process_origin).replace(/\/$/, "") : "";
    lan = data && data.origin ? String(data.origin).replace(/\/$/, "") : "";
  } catch (err) {}
  const base = process || lan || (await hostOrigin());
  let url = base + "/m.html?room=" + state.room.code + "&v=queue3";
  if (lan && process && lan !== process) url += "&lan=" + encodeURIComponent(lan);
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

