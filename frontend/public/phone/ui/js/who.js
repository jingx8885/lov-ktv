import { $ } from "../../../shared/ui/js/dom.js";
import { api } from "../../api.js";
import { paintTopWho } from "./icons.js";
import { showToast } from "./toast.js";

export function loginQs() {
  const q = new URLSearchParams();
  if ($("room").value) q.set("room", $("room").value.trim().toUpperCase());
  q.set("next", location.pathname + location.search);
  return "/api/auth/scan?" + q.toString();
}

export async function loadWho() {
  const data = await fetch("/api/auth/me", { credentials: "same-origin" }).then((r) => r.json()).catch(() => ({ user: null }));
  const user = data.user;
  $("whoName").textContent = user ? (user.sid || user.nickname || "已登录") : "未登录";
  $("whoHint").textContent = user ? (user.wechat ? "微信 ID 已锁定" : "本机 ID") : "微信扫一下就能认号";
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
    showToast("已退出");
  };
  loadWho();
}

api.loadWho = loadWho;
