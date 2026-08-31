import { t, bootI18n, onLangChange, applyDom } from "../../shared/i18n/js/i18n.js";

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const hero = document.querySelector(".lp-hero");
const shot = document.querySelector(".lp-shot");
if (hero && !reduced) {
  const move = (event) => {
    const box = hero.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * 100;
    const y = ((event.clientY - box.top) / box.height) * 100;
    hero.style.setProperty("--spot-x", `${x}%`);
    hero.style.setProperty("--spot-y", `${y}%`);
    if (!shot) return;
    const card = shot.getBoundingClientRect();
    const cx = (event.clientX - card.left) / card.width;
    const cy = (event.clientY - card.top) / card.height;
    shot.style.setProperty("--glare-x", `${cx * 100}%`);
    shot.style.setProperty("--glare-y", `${cy * 100}%`);
    shot.style.setProperty("--tilt-y", `${((cx - 0.5) * 8).toFixed(2)}deg`);
    shot.style.setProperty("--tilt-x", `${((0.5 - cy) * 6).toFixed(2)}deg`);
  };
  window.addEventListener("pointermove", move, { passive: true });
}

document.querySelectorAll(".lp-features article").forEach((card) => {
  card.addEventListener(
    "pointermove",
    /** @param {PointerEvent} event */ (event) => {
      const box = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${event.clientX - box.left}px`);
      card.style.setProperty("--my", `${event.clientY - box.top}px`);
    },
    { passive: true }
  );
});

bootI18n();

const songs = [
  {
    song: "夜曲",
    artist: "周杰伦",
    prev: "一群嗜血的蚂蚁 被腐肉所吸引",
    cur: "我却得到你的纵容 神的原谅",
    next: "而你 却沉默地转过身",
    vocal: false,
    queue: [
      { role: "now", artist: "周杰伦" },
      { role: "next", artist: "imase" },
      { role: "wait", artist: "Ed Sheeran" }
    ]
  },
  {
    song: "NIGHT DANCER",
    artist: "imase",
    prev: "夜の街を抜けて",
    cur: "君の声がまだ残ってる",
    next: "踊り続けて NIGHT DANCER",
    vocal: true,
    queue: [
      { role: "now", artist: "imase" },
      { role: "next", artist: "Ed Sheeran" },
      { role: "wait", artist: "周杰伦" }
    ]
  },
  {
    song: "Shape of You",
    artist: "Ed Sheeran",
    prev: "The club isn't the best place",
    cur: "to find a lover so the bar is where I go",
    next: "Me and my friends at the table",
    vocal: false,
    queue: [
      { role: "now", artist: "Ed Sheeran" },
      { role: "next", artist: "周杰伦" },
      { role: "wait", artist: "imase" }
    ]
  }
];

const ROLE_KEY = { now: "landing.demo.now", next: "landing.demo.next", wait: "landing.demo.wait" };

const $ = (id) => document.getElementById(id);
const songEl = $("demoSong");
const artistEl = $("demoArtist");
const prevEl = $("demoPrev");
const curEl = $("demoCur");
const nextEl = $("demoNext");
const modeEl = $("demoMode");
const queueEls = document.querySelectorAll("[data-demo-role]");

let index = 0;

function paintSong() {
  const item = songs[index];
  if (!item) return;
  if (songEl) songEl.textContent = item.song;
  if (artistEl) artistEl.textContent = item.artist;
  if (prevEl) prevEl.textContent = item.prev;
  if (curEl) curEl.innerHTML = `<span>${item.cur}</span>`;
  if (nextEl) nextEl.textContent = item.next;
  if (modeEl) modeEl.textContent = item.vocal ? t("common.vocal") : t("common.karaoke");
  queueEls.forEach((el, i) => {
    const row = item.queue[i] || { role: el.getAttribute("data-demo-role") || "wait", artist: item.artist };
    el.textContent = t(ROLE_KEY[row.role] || ROLE_KEY.wait, { artist: row.artist });
  });
}

let appCatalog = null;

onLangChange(() => {
  applyDom();
  paintSong();
  paintAppDownloads(appCatalog);
});

if (songEl && curEl) {
  paintSong();
  if (!reduced) {
    setInterval(() => {
      index = (index + 1) % songs.length;
      paintSong();
    }, 4200);
  }
}

function formatSize(bytes) {
  const n = Number(bytes) || 0;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n >= 1000) return `${Math.round(n / 1000)} KB`;
  return `${n} B`;
}

function versionedAppUrl(raw, item) {
  const href = String(raw || "").trim();
  if (!href) return "";
  const version = String((item && (item.version || item.sha256)) || "").trim();
  if (!version) return href;
  return `${href}${href.includes("?") ? "&" : "?"}v=${encodeURIComponent(version)}`;
}

function paintAppDownloads(catalog) {
  const data = catalog && typeof catalog === "object" ? catalog : {};
  const ready = ["tv", "phone"].filter((name) => data[name] && data[name].url);
  document.querySelectorAll(".cta-apps").forEach((row) => {
    row.hidden = ready.length === 0;
  });
  document.querySelectorAll("[data-app]").forEach((el) => {
    const name = el.getAttribute("data-app") || "";
    const item = data[name];
    el.hidden = !item;
    if (!item) return;
    if (item.url) el.setAttribute("href", versionedAppUrl(item.url, item));
    const ver = el.querySelector(".ver");
    if (ver) ver.textContent = t("landing.apps.ver", { version: item.version || "", size: formatSize(item.size) });
  });
}

fetch("/api/apps")
  .then((resp) => (resp.ok ? resp.json() : null))
  .then((catalog) => {
    appCatalog = catalog;
    paintAppDownloads(appCatalog);
  })
  .catch(() => paintAppDownloads(null));
