import { $ } from "../../../../shared/ui/js/dom.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";

const PEEK_PORT = 58;
const PEEK_LAND = 48;
const OPEN_RATIO = 0.78;
const LAND_OPEN_RATIO = 0.92;
const HYSTERESIS = 10;
const FLICK = 680;

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function landscape() {
  return window.matchMedia("(orientation: landscape)").matches;
}

function desktopLayout() {
  return window.matchMedia("(min-width: 900px)").matches;
}

function peekSize() {
  return landscape() ? PEEK_LAND : PEEK_PORT;
}

function openHeight() {
  const main = $("playerMain");
  const h = main ? main.clientHeight : window.innerHeight;
  const ratio = landscape() ? LAND_OPEN_RATIO : OPEN_RATIO;
  return Math.max(peekSize() + 80, Math.round(h * ratio));
}

function peekY() {
  return Math.max(0, openHeight() - peekSize());
}

function liveY(sheet) {
  const t = getComputedStyle(sheet).transform;
  if (!t || t === "none") return Number(sheet.dataset.y || peekY());
  return new DOMMatrix(t).m42;
}

function applySheet(y, anim, hard = true) {
  const sheet = $("playerSheet");
  if (!sheet) return;
  if (desktopLayout()) {
    sheet.style.height = "";
    sheet.style.removeProperty("--sheet-peek");
    sheet.style.transform = "none";
    sheet.classList.remove("is-anim", "is-drag");
    sheet.classList.add("is-open");
    sheet.dataset.y = "0";
    sheet.dataset.snap = "open";
    document.body.classList.remove("player-sheet-open");
    const grab = $("playerSheetGrab");
    if (grab) {
      grab.setAttribute("aria-expanded", "true");
      grab.setAttribute("aria-label", t("phone.player.closeLib"));
    }
    const scrim = $("playerSheetScrim");
    if (scrim) scrim.hidden = true;
    return;
  }
  const open = openHeight();
  const peek = peekY();
  const next = hard ? Math.max(0, Math.min(peek, y)) : y;
  sheet.style.height = `${open}px`;
  sheet.style.setProperty("--sheet-peek", `${peekSize()}px`);
  sheet.classList.toggle("is-anim", !!anim && !reducedMotion());
  sheet.classList.toggle("is-drag", !anim);
  sheet.style.transform = `translate3d(0, ${next}px, 0)`;
  sheet.dataset.y = String(next);
  const snap = next < peek * 0.45 ? "open" : "peek";
  sheet.dataset.snap = snap;
  sheet.classList.toggle("is-open", snap === "open");
  document.body.classList.toggle("player-sheet-open", snap === "open");
  const grab = $("playerSheetGrab");
  if (grab) {
    grab.setAttribute("aria-expanded", snap === "open" ? "true" : "false");
    grab.setAttribute("aria-label", snap === "open" ? t("phone.player.closeLib") : t("phone.player.openLib"));
  }
  const scrim = $("playerSheetScrim");
  if (scrim) scrim.hidden = snap !== "open";
}

function project(velocity, decel = 0.998) {
  return ((velocity / 1000) * decel) / (1 - decel);
}

function rubber(overshoot, dim, constant = 0.55) {
  return (overshoot * dim * constant) / (dim + constant * Math.abs(overshoot));
}

function clampDrag(y) {
  const peek = peekY();
  if (y < 0) return -rubber(-y, openHeight());
  if (y > peek) return peek + rubber(y - peek, openHeight());
  return y;
}

export function setPlayerSheet(snap, anim = true) {
  applySheet(snap === "open" ? 0 : peekY(), anim);
}

export function syncPlayerSheet() {
  const sheet = $("playerSheet");
  if (!sheet) return;
  const snap = sheet.dataset.snap === "open" ? "open" : "peek";
  applySheet(snap === "open" ? 0 : peekY(), false);
}

export function syncPlayerSheetMeta() {
  const count = (state.playerCatalog || []).length;
  const title = $("playerSheetTitle");
  const meta = $("playerSheetMeta");
  if (title) title.textContent = t("phone.desk.lib");
  if (meta) meta.textContent = count ? t("phone.desk.nSongs", { n: count }) : t("phone.player.noPlayable");
}

export function bindPlayerSheet() {
  const sheet = $("playerSheet");
  const grab = $("playerSheetGrab");
  const list = $("playerList");
  const scrim = $("playerSheetScrim");
  if (!sheet || !grab) return;

  let drag = null;
  const samples = [];

  const pushSample = (y, t) => {
    samples.push({ y, t });
    if (samples.length > 5) samples.shift();
  };

  const velocity = () => {
    if (samples.length < 2) return 0;
    const a = samples[0];
    const b = samples[samples.length - 1];
    const dt = Math.max(1, b.t - a.t);
    return ((b.y - a.y) / dt) * 1000;
  };

  const startDrag = (e, from, capture) => {
    const startY = liveY(sheet);
    drag = {
      id: e.pointerId,
      from,
      grab: e.clientY - startY,
      origin: startY,
      startClientY: e.clientY,
      target: capture || grab,
      moved: false
    };
    samples.length = 0;
    pushSample(startY, e.timeStamp);
    sheet.classList.add("is-drag");
    sheet.classList.remove("is-anim");
    if (capture !== false) {
      try {
        (capture || grab).setPointerCapture(e.pointerId);
      } catch (err) {}
    }
  };

  const moveDrag = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const raw = e.clientY - drag.grab;
    if (!drag.moved && Math.abs(raw - drag.origin) < HYSTERESIS) return;
    drag.moved = true;
    const y = clampDrag(raw);
    applySheet(y, false, false);
    pushSample(y, e.timeStamp);
  };

  const endDrag = (e) => {
    if (!drag || (e && e.pointerId !== drag.id)) return;
    const y = liveY(sheet);
    const v = velocity();
    const peek = peekY();
    let snap = y < peek / 2 ? "open" : "peek";
    if (Math.abs(v) > FLICK) snap = v > 0 ? "peek" : "open";
    else {
      const projected = y + project(v);
      snap = projected < peek / 2 ? "open" : "peek";
    }
    if (!drag.moved && drag.from === "grab") snap = sheet.dataset.snap === "open" ? "peek" : "open";
    drag = null;
    samples.length = 0;
    setPlayerSheet(snap, true);
  };

  grab.addEventListener("pointerdown", (e) => {
    if (e.button) return;
    startDrag(e, "grab", grab);
  });
  grab.addEventListener("pointermove", moveDrag);
  grab.addEventListener("pointerup", endDrag);
  grab.addEventListener("pointercancel", endDrag);

  if (list) {
    list.addEventListener("pointerdown", (e) => {
      if (e.button || sheet.dataset.snap !== "open" || list.scrollTop > 1) return;
      startDrag(e, "list", false);
    });
    list.addEventListener(
      "pointermove",
      (e) => {
        if (!drag || drag.from !== "list" || e.pointerId !== drag.id) return;
        if (!drag.moved && e.clientY < drag.startClientY) {
          drag = null;
          sheet.classList.remove("is-drag");
          return;
        }
        if (!drag.moved && e.clientY - drag.startClientY >= HYSTERESIS) {
          try {
            list.setPointerCapture(e.pointerId);
          } catch (err) {}
        }
        moveDrag(e);
        if (drag && drag.moved) e.preventDefault();
      },
      { passive: false }
    );
    list.addEventListener("pointerup", endDrag);
    list.addEventListener("pointercancel", endDrag);
  }

  if (scrim) scrim.onclick = () => setPlayerSheet("peek", true);

  window.addEventListener("resize", () => {
    if ($("page-player") && !$("page-player").hidden) syncPlayerSheet();
  });
  window.addEventListener("orientationchange", () => {
    requestAnimationFrame(() => syncPlayerSheet());
  });

  setPlayerSheet("peek", false);
  syncPlayerSheetMeta();
}
