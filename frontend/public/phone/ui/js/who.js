import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { paintTopWho } from "./icons.js";
import { showToast } from "./toast.js";

export function loginQs() {
  const q = new URLSearchParams();
  if ($("room").value) q.set("room", $("room").value.trim().toUpperCase());
  q.set("next", location.pathname + location.search);
  return "/api/auth/scan?" + q.toString();
}

export async function loadWho() {
  const { data } = await fetchJson("/api/auth/me", { credentials: "same-origin" }).catch(() => ({ data: { user: null } }));
  const user = data.user;
  $("whoName").textContent = user ? (user.sid || user.nickname || t("phone.who.in")) : t("phone.who.out");
  $("whoHint").textContent = user ? (user.wechat ? t("phone.who.wechat") : t("phone.who.device")) : t("phone.who.hint");
  $("whoLogin").hidden = !!user;
  $("whoLogin").href = loginQs();
  $("whoLogout").hidden = !user;
  if (user && user.avatar) {
    $("whoAvatar").hidden = false;
    $("whoAvatar").src = user.avatar;
    $("topWho").innerHTML = `<img alt="" src="${user.avatar}">`;
  } else {
    $("whoAvatar").hidden = true;
    paintTopWho(user);
  }
}

export function bindWho() {
  $("whoLogout").onclick = async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    await loadWho();
    showToast(t("phone.who.bye"));
  };
  loadWho();
}

