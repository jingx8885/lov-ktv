import { $ } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { showToast } from "./toast.js";
import { loadWho, promptLogin } from "./who.js";
import { hasNativePhone, phonePlatform } from "../../platform.js";

let token = "";
let remain = 0;
let timer = 0;
let placement = "wait";
let lastPoints = null;

function nativeOpen(url) {
  try {
    if (hasNativePhone() && phonePlatform.remote.open(url)) return true;
  } catch (_) {}
  return false;
}

function jumpTo(url) {
  if (!url) return;
  if (nativeOpen(url)) return;
  const abs = new URL(url, location.origin).toString();
  window.open(abs, "_blank") || (location.href = abs);
}

export function paintPoints(points) {
  lastPoints = points || lastPoints;
  const el = $("whoPoints");
  if (!el) return;
  const n = lastPoints && typeof lastPoints.balance === "number" ? lastPoints.balance : 0;
  el.hidden = false;
  el.textContent = t("phone.who.points", { n });
}

function closeAd() {
  clearInterval(timer);
  timer = 0;
  token = "";
  const layer = $("adLayer");
  if (layer) layer.hidden = true;
}

function tick() {
  remain = Math.max(0, remain - 1);
  const label = $("adTimer");
  if (label) {
    label.textContent = remain > 0 ? t("ads.remain", { n: remain }) : t("ads.done");
  }
  const skip = $("adSkip");
  if (skip) skip.hidden = remain > 25;
  if (remain <= 0) {
    clearInterval(timer);
    timer = 0;
    finishAd();
  }
}

async function finishAd() {
  if (!token) return;
  const { ok, data } = await fetchJson("/api/ads/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  });
  if (ok) {
    paintPoints(data.points);
    showToast(t("ads.earned"));
    loadWho();
  } else {
    showToast(data.detail || t("api.ad_invalid"));
  }
  closeAd();
}

export async function showAd(kind) {
  placement = kind === "splash" ? "splash" : "wait";
  const layer = $("adLayer");
  if (!layer) return false;
  const response = await fetchJson("/api/ads/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ placement })
  }).catch(() => null);
  if (!response) {
    closeAd();
    return false;
  }
  const { ok, status, data } = response;
  if (!ok) {
    closeAd();
    if (status !== 204 && status !== 404 && data && data.detail) showToast(data.detail);
    return false;
  }
  const ad = data && data.ad;
  // An upstream response without an ad is a no-op. Do not flash an empty
  // ad card (especially on splash) or start a timer without a claim token.
  if (!ad || typeof ad !== "object" || !ad.id || !data.token) {
    closeAd();
    return false;
  }
  const url = ad.url || "";
  token = data.token;
  remain = Number(ad.seconds || 30);
  paintPoints(data.points);
  $("adKind").textContent = placement === "splash" ? t("ads.splash") : t("ads.wait");
  $("adTitle").textContent = ad.title || "";
  $("adBody").textContent = ad.body || "";
  $("adJump").textContent = ad.cta || t("ads.watch");
  $("adJump").dataset.url = url;
  $("adJump").hidden = !url;
  $("adImage").src = ad.image || "/brand/icon.png";
  $("adTimer").textContent = t("ads.remain", { n: remain });
  $("adSkip").hidden = true;
  layer.hidden = false;
  clearInterval(timer);
  timer = setInterval(tick, 1000);
  return true;
}

export function promptPoints() {
  showAd("wait");
}

export async function claimDownloadIfNative() {
  if (!hasNativePhone()) return;
  const { ok, data } = await fetchJson("/api/points/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "download" })
  });
  if (ok) {
    paintPoints(data);
    showToast(t("phone.who.points", { n: data.balance }));
    loadWho();
  }
}

export function bindAds() {
  const jump = $("adJump");
  if (jump) {
    jump.onclick = async () => {
      const { data } = await fetchJson("/api/ads/click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token })
      }).catch(() => ({ data: {} }));
      jumpTo(data.url || jump.dataset.url || "");
    };
  }
  const skip = $("adSkip");
  if (skip) skip.onclick = closeAd;
  const watch = $("whoWatchAd");
  if (watch) watch.onclick = () => showAd("wait");
}

export function bootAds() {
  bindAds();
  claimDownloadIfNative();
}

export function handlePointError(status, detail) {
  showToast(detail || t("api.need_points", { cost: "?", have: "0" }));
  if (status === 402) promptPoints();
  if (status === 429) promptLogin();
}
