import { connection, allowedPath } from "./policy.js";
const $ = (id) => document.getElementById(id);
const native = window.Capacitor?.registerPlugin("Remote");
const later = typeof setTimeout === "function" ? setTimeout : () => 0;
const cancel = typeof clearTimeout === "function" ? clearTimeout : () => {};
const TABS = { remote: "遥控", library: "曲库", settings: "设置" };
const BUSY = ["queued", "fetching", "separating", "aligning", "annotating", "running"];
let config = null,
  snapshot = null,
  page = 1,
  generation = 0,
  refreshing = false,
  current = "settings",
  toastTimer = 0,
  searchTimer = 0;

/* ---------------- small DOM helpers ---------------- */
const attr = (el, key, value) => el?.setAttribute?.(key, String(value));
const each = (selector, run) => {
  for (const el of document.querySelectorAll(selector)) run(el);
};
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function svg(path) {
  const span = el("span", "glyph");
  span.setAttribute("aria-hidden", "true");
  // Static, app-owned markup only; never interpolate server data here.
  span.innerHTML = `<svg viewBox="0 0 24 24">${path}</svg>`;
  return span;
}
const ICON = {
  more: '<circle cx="5" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="19" cy="12" r="2" fill="currentColor"/>',
  plus: '<path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>',
};
const PALETTE = [
  ["#ff5f6d", "#ffc371"],
  ["#5f72ff", "#9b5cff"],
  ["#00b4db", "#0083b0"],
  ["#f7971e", "#ffd200"],
  ["#11998e", "#38ef7d"],
  ["#ee0979", "#ff6a00"],
  ["#8e2de2", "#ff4b8b"],
  ["#4facfe", "#00f2fe"],
];
function paint(node, seed) {
  let hash = 0;
  for (const ch of String(seed || "")) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  const [a, b] = PALETTE[hash % PALETTE.length];
  node?.style?.setProperty?.("--art-a", a);
  node?.style?.setProperty?.("--art-b", b);
}
const firstGlyph = (text) => [...String(text || "").trim()][0] || "♪";

/* ---------------- status toast ---------------- */
const status = (message) => {
  const toast = $("status");
  toast.textContent = message;
  attr(toast, "data-show", message ? "true" : "false");
  cancel(toastTimer);
  if (message)
    toastTimer = later(() => attr(toast, "data-show", "false"), 2800);
};

const read = (key, fallback) => {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
};
let blocked = read("remote-blocked", {});
function hidden(id) {
  return (blocked[config?.server] || []).includes(id);
}
function block(id) {
  blocked[config.server] = [...new Set([...(blocked[config.server] || []), id])];
  localStorage.setItem("remote-blocked", JSON.stringify(blocked));
}

/* ---------------- navigation ---------------- */
function tab(id) {
  current = id;
  for (const name of Object.keys(TABS)) $(name).hidden = name !== id;
  for (const button of document.querySelectorAll("[data-tab]"))
    button.setAttribute(
      "aria-current",
      button.dataset.tab === id ? "page" : "false",
    );
  $("bar-title").textContent = TABS[id];
  window.scrollTo?.(0, 0);
  onScroll();
}
function onScroll() {
  attr($("bar"), "data-scrolled", (window.scrollY || 0) > 34 ? "true" : "false");
}
function connectedUi() {
  const on = !!config;
  attr($("app"), "data-connected", on);
  $("conn-title").textContent = on
    ? config.mode === "official"
      ? "已连接 · 官方服务"
      : "已连接 · 自己的服务器"
    : "未连接";
  $("conn-detail").textContent = on
    ? `${config.server.replace(/^https?:\/\//, "")} · 房间 ${config.room}`
    : "连接自己的服务器或官方服务";
  $("now-room").textContent = on ? config.room : "";
  const submit = document.querySelector?.('#connect [type="submit"]');
  if (submit) submit.textContent = on ? "重新连接" : "连接服务器";
}

/* ---------------- action sheet ---------------- */
function sheet(title, actions) {
  const root = $("sheet");
  const list = $("sheet-actions");
  if (!root || !list?.append) return;
  $("sheet-title").textContent = title;
  list.replaceChildren();
  for (const item of actions) {
    const b = el("button", `sheet-action${item.danger ? " danger" : ""}`, item.label);
    b.type = "button";
    b.onclick = () => {
      closeSheet();
      action(item.run);
    };
    list.append(b);
  }
  root.hidden = false;
  later(() => attr(root, "data-open", "true"), 16);
}
function closeSheet() {
  const root = $("sheet");
  if (!root || root.hidden) return;
  attr(root, "data-open", "false");
  later(() => {
    if (root.getAttribute?.("data-open") !== "true") root.hidden = true;
  }, 260);
}
each("[data-sheet-close]", (node) => (node.onclick = closeSheet));

/* ---------------- networking ---------------- */
async function request(path, body) {
  if (!config || !native) throw new Error("请先在 iOS App 内连接服务器");
  const method = body === undefined ? "GET" : "POST";
  if (!allowedPath(path, method)) throw new Error("不支持此操作");
  const result = await native.request({
    path,
    method,
    body: body === undefined ? "" : JSON.stringify(body),
  });
  if (result.status < 200 || result.status >= 300)
    throw new Error(
      config.mode === "official" && [401, 403].includes(result.status)
        ? "API key 无效或已失效"
        : result.status === 402
          ? "服务器未允许点歌，请联系服务器管理员。"
          : `服务器请求失败（${result.status}）`,
    );
  return JSON.parse(result.body);
}
async function action(work) {
  try {
    await work();
  } catch (error) {
    status(error.message || "操作失败，请重试");
  }
}
function resetViews() {
  $("songs").replaceChildren();
  $("queue").replaceChildren();
  $("now").textContent = "暂无播放";
  $("now-artist").textContent = "";
  attr($("now-art"), "data-empty", "true");
  $("queue-count").textContent = "";
  $("queue-badge").hidden = true;
}
async function connect(candidate, apiKey = "") {
  generation++;
  page = 1;
  config = null;
  snapshot = null;
  resetViews();
  connectedUi();
  await native.configure({
    server: candidate.server,
    official: candidate.mode === "official",
    apiKey,
  });
  $("api-key").value = "";
  config = candidate;
  localStorage.setItem("remote-config", JSON.stringify(config));
  $("server").value = config.server;
  $("room").value = config.room;
  connectedUi();
  await refresh();
  await search();
  tab("remote");
  status(config.mode === "official" ? "已连接官方服务" : "已连接自己的服务器");
}

/* ---------------- now playing + queue ---------------- */
async function refresh() {
  if (!config) return;
  const epoch = generation;
  const data = await request(`/api/rooms/${config.room}`);
  if (epoch !== generation) return;
  snapshot = data;
  const song = data.now_playing;
  const masked = song && hidden(song.song_id || song.id);
  $("now").textContent = song
    ? masked
      ? "当前内容已屏蔽"
      : song.title || "未命名"
    : "暂无播放";
  $("now-artist").textContent = song && !masked ? song.artist || "" : song ? "" : "去曲库点一首歌吧";
  $("now-label").textContent = song ? (data.paused ? "已暂停" : "正在播放") : "空闲";
  const art = $("now-art");
  attr(art, "data-empty", song && !masked ? "false" : "true");
  if (song && !masked) {
    $("now-glyph").textContent = firstGlyph(song.title);
    paint(art, song.title);
  }
  const play = $("play");
  play.disabled = !song;
  attr(play, "data-paused", data.paused || !song ? "true" : "false");
  attr(play, "aria-label", data.paused ? "继续播放" : "暂停播放");
  if (document.activeElement !== $("volume")) {
    $("volume").value = data.volume ?? 70;
    fillVolume();
  }
  const queue = (data.queue || []).filter((s) => !hidden(s.song_id || s.id));
  $("queue-count").textContent = queue.length ? String(queue.length) : "";
  const badge = $("queue-badge");
  badge.hidden = !queue.length;
  badge.textContent = queue.length > 99 ? "99+" : String(queue.length);
  render($("queue"), data.queue || [], false);
}
function fillVolume() {
  const range = $("volume");
  range?.style?.setProperty?.("--vol", `${Number(range.value) || 0}%`);
}

/* ---------------- song rows ---------------- */
function badgeFor(song) {
  if (!song.status || song.status === "ready") return null;
  if (song.status === "failed" || song.status === "error") return ["处理失败", "bad"];
  if (BUSY.includes(song.status)) return ["处理中", "busy"];
  return null;
}
function render(root, songs, enqueue) {
  root.replaceChildren();
  let index = 0;
  for (const song of songs.filter((song) => !hidden(song.song_id || song.id))) {
    index++;
    const id = song.song_id || song.id;
    const row = el("article", "song-row");
    if (!enqueue) row.append(el("span", "rank", String(index)));
    const art = el("div", "art", firstGlyph(song.title));
    art.setAttribute("aria-hidden", "true");
    paint(art, song.title);
    row.append(art);
    const text = el("div", "song-text");
    text.append(el("p", "song-title", song.title || "未命名"));
    const sub = el("p", "song-artist", song.artist || "未知歌手");
    const tag = badgeFor(song);
    if (tag) sub.prepend(el("span", `tag ${tag[1]}`, tag[0]));
    text.append(sub);
    row.append(text);

    const guard = (button, run) => async () => {
      button.disabled = true;
      try {
        await run();
      } finally {
        button.disabled = false;
      }
    };
    const ready = song.status === "ready";
    const listen = async () => {
      status("正在下载服务器音频…");
      showListening(song, "正在下载…");
      try {
        await native.listen({ id });
      } catch (error) {
        hideListening();
        throw error;
      }
      showListening(song, song.title || "未命名");
      status("正在手机播放，可锁屏收听");
    };
    const remove = (message) => {
      row.remove();
      if ((snapshot?.now_playing?.song_id || snapshot?.now_playing?.id) === id) {
        $("now").textContent = "当前内容已屏蔽";
        $("now-artist").textContent = "";
        attr($("now-art"), "data-empty", "true");
      }
      if (!root.children.length) empty(root, enqueue);
      status(message);
    };
    const blockIt = async () => {
      await native.stop();
      hideListening();
      block(id);
      remove("已在此设备屏蔽该内容");
    };
    const reportIt = async () => {
      await native.stop();
      hideListening();
      const reason = prompt("举报原因（不当内容、侵权或其他，最多 500 字）");
      if (!reason?.trim()) return;
      await request("/api/remote/reports", {
        song_id: id,
        reason: reason.trim().slice(0, 500),
      });
      block(id);
      remove("举报已送达服务器管理员，内容已在本机屏蔽");
    };

    if (enqueue && ready) {
      const add = el("button", "pill", "点歌");
      add.type = "button";
      add.setAttribute("aria-label", `点歌：${song.title || "未命名"}`);
      add.onclick = () =>
        action(
          guard(add, async () => {
            await request(`/api/rooms/${config.room}/queue`, { song_id: id });
            add.textContent = "已点";
            attr(add, "data-done", "true");
            await refresh();
            status("已加入队列");
            later(() => {
              add.textContent = "点歌";
              attr(add, "data-done", "false");
            }, 1600);
          }),
        );
      row.append(add);
    }
    const more = el("button", "more");
    more.type = "button";
    more.setAttribute("aria-label", `更多操作：${song.title || "未命名"}`);
    more.append(svg(ICON.more));
    more.onclick = () =>
      sheet(`${song.title || "未命名"} · ${song.artist || "未知歌手"}`, [
        ...(enqueue && ready ? [{ label: "手机试听", run: listen }] : []),
        { label: "屏蔽", danger: true, run: blockIt },
        { label: "举报并屏蔽", danger: true, run: reportIt },
      ]);
    row.append(more);
    root.append(row);
  }
  if (!root.children.length) empty(root, enqueue);
}
function empty(root, enqueue) {
  if (!document.createElement) {
    root.textContent = "暂无可显示的歌曲";
    return;
  }
  const query = $("query")?.value?.trim();
  const box = el("div", "list-empty");
  box.append(
    el(
      "p",
      "list-empty-title",
      enqueue ? (query ? "没有找到相关歌曲" : "暂无可显示的歌曲") : "队列空空的",
    ),
  );
  box.append(
    el(
      "p",
      "list-empty-text",
      enqueue
        ? query
          ? "换个歌名或歌手试试。"
          : "服务器曲库里还没有可唱的歌。"
        : "去曲库点首歌，它会出现在这里。",
    ),
  );
  root.append(box);
}

/* ---------------- phone preview mini player ---------------- */
function showListening(song, title) {
  const bar = $("listening");
  if (!bar) return;
  bar.hidden = false;
  $("listening-title").textContent = title;
  const art = $("listening-art");
  art.textContent = firstGlyph(song.title);
  paint(art, song.title);
  attr($("app"), "data-listening", "true");
}
function hideListening() {
  const bar = $("listening");
  if (bar) bar.hidden = true;
  attr($("app"), "data-listening", "false");
}

/* ---------------- library search ---------------- */
async function search() {
  const epoch = generation;
  const songs = $("songs");
  attr(songs, "aria-busy", "true");
  try {
    const data = await request(
      `/api/songs?q=${encodeURIComponent($("query").value.trim())}&page=${page}&count=20`,
    );
    if (epoch !== generation) return;
    render(songs, data.songs || [], true);
    $("more").hidden = page * 20 >= (data.total || 0);
    attr($("more"), "data-page", `${page} / ${Math.max(1, Math.ceil((data.total || 0) / 20))}`);
  } finally {
    attr(songs, "aria-busy", "false");
  }
}

/* ---------------- event wiring ---------------- */
$("connect").onsubmit = (event) => {
  event.preventDefault();
  document.activeElement?.blur?.();
  action(() => {
    const mode = $("mode").value;
    const candidate = connection(
      mode === "official" ? "https://ktv.lovbrowser.com" : $("server").value,
      $("room").value,
    );
    return connect(
      {
        ...candidate,
        mode:
          candidate.server === "https://ktv.lovbrowser.com" ? "official" : mode,
      },
      $("api-key").value.trim(),
    );
  });
};
$("scan").onclick = () =>
  action(async () => {
    const result = await native.scan();
    const candidate = connection(result.value);
    $("server").value = candidate.server;
    $("room").value = candidate.room;
    status("二维码已填入，请核对地址后点击连接服务器");
  });
$("search").onsubmit = (event) => {
  event.preventDefault();
  cancel(searchTimer);
  document.activeElement?.blur?.();
  page = 1;
  action(search);
};
$("query").oninput = () => {
  cancel(searchTimer);
  if (!config) return;
  searchTimer = later(() => {
    page = 1;
    action(search);
  }, 400);
};
$("more").onclick = () =>
  action(async () => {
    page++;
    await search();
    window.scrollTo?.({ top: 0, behavior: "smooth" });
  });
$("play").onclick = () =>
  action(async () => {
    if (!snapshot) throw new Error("请先连接房间");
    await request(`/api/rooms/${config.room}/mix`, {
      paused: !snapshot.paused,
    });
    await refresh();
  });
$("skip").onclick = () =>
  action(async () => {
    if (!config) throw new Error("请先连接房间");
    sheet("切换到下一首？当前歌曲会立即停止。", [
      {
        label: "下一首",
        danger: true,
        run: async () => {
          await request(`/api/rooms/${config.room}/skip`, {});
          await refresh();
        },
      },
    ]);
  });
$("volume").oninput = fillVolume;
$("volume").onchange = () =>
  action(async () => {
    if (!config) throw new Error("请先连接房间");
    await request(`/api/rooms/${config.room}/mix`, {
      volume: Number($("volume").value),
    });
  });
async function forget() {
  generation++;
  config = null;
  snapshot = null;
  blocked = {};
  localStorage.removeItem("remote-config");
  localStorage.removeItem("remote-blocked");
  await native.configure({ server: "" });
  hideListening();
  $("server").value = "";
  $("room").value = "";
  $("api-key").value = "";
  resetViews();
  connectedUi();
  status("已清除本机数据");
  tab("settings");
}
$("forget").onclick = () => {
  if ($("sheet")?.setAttribute && document.createElement)
    sheet("断开连接并删除本机保存的地址、房间码、屏蔽列表和 API key？", [
      { label: "断开并清除", danger: true, run: forget },
    ]);
  else action(forget);
};
$("unblock").onclick = () => {
  blocked = {};
  localStorage.removeItem("remote-blocked");
  status("已清除屏蔽列表");
  if (config) action(async () => Promise.all([refresh(), search()]));
};
$("stop-audio").onclick = () =>
  action(async () => {
    await native.stop();
    hideListening();
    status("手机试听已停止");
  });
for (const button of document.querySelectorAll("[data-tab]"))
  button.onclick = () => tab(button.dataset.tab);
each("[data-go]", (button) => (button.onclick = () => tab(button.dataset.go)));
each("[data-mode]", (button) => {
  button.onclick = () => {
    if ($("mode").value === button.dataset.mode) return;
    $("mode").value = button.dataset.mode;
    connectionFields();
  };
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && config) action(refresh);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeSheet();
});
window.addEventListener?.("scroll", onScroll, { passive: true });
setInterval(() => {
  if (config && !document.hidden && !refreshing) {
    refreshing = true;
    action(refresh).finally(() => {
      refreshing = false;
    });
  }
}, 3000);
tab("settings");
function connectionFields() {
  const official = $("mode").value === "official";
  $("key-field").hidden = !official;
  $("official-hint").hidden = !official;
  $("server-field").hidden = official;
  $("server").required = !official;
  $("scan").hidden = official;
  $("api-key").value = "";
  attr($("mode-seg"), "data-value", official ? "official" : "self");
  each("[data-mode]", (button) =>
    attr(button, "aria-checked", button.dataset.mode === $("mode").value),
  );
}
$("mode").onchange = connectionFields;
const saved = read("remote-config", null);
if (saved) {
  $("mode").value = saved.mode === "official" ? "official" : "self";
  $("server").value = saved.server;
  $("room").value = saved.room;
}

connectionFields();
connectedUi();
fillVolume();
