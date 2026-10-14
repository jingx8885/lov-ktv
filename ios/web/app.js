import { connection, allowedPath } from "./policy.js";
const $ = (id) => document.getElementById(id);
const native = window.Capacitor?.registerPlugin("Remote");
let config = null,
  snapshot = null,
  page = 1,
  generation = 0,
  refreshing = false;
const status = (message) => {
  $("status").textContent = message;
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
function tab(id) {
  for (const name of ["settings", "library", "remote"])
    $(name).hidden = name !== id;
  for (const button of document.querySelectorAll("[data-tab]"))
    button.setAttribute(
      "aria-current",
      button.dataset.tab === id ? "page" : "false",
    );
}
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
async function connect(candidate, apiKey = "") {
  generation++;
  page = 1;
  config = null;
  snapshot = null;
  $("songs").replaceChildren();
  $("queue").replaceChildren();
  $("now").textContent = "暂无播放";
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
  await refresh();
  await search();
  tab("remote");
  status(config.mode === "official" ? "已连接官方服务" : "已连接自己的服务器");
}
async function refresh() {
  if (!config) return;
  const epoch = generation;
  const data = await request(`/api/rooms/${config.room}`);
  if (epoch !== generation) return;
  snapshot = data;
  $("now").textContent = data.now_playing
    ? hidden(data.now_playing.song_id || data.now_playing.id)
      ? "当前内容已屏蔽"
      : `${data.now_playing.title || "未命名"} · ${data.now_playing.artist || ""}`
    : "暂无播放";
  $("play").textContent = data.paused ? "继续播放" : "暂停播放";
  if (document.activeElement !== $("volume"))
    $("volume").value = data.volume ?? 70;
  render($("queue"), data.queue || [], false);
}
function render(root, songs, enqueue) {
  root.replaceChildren();
  for (const song of songs.filter((song) => !hidden(song.song_id || song.id))) {
    const id = song.song_id || song.id;
    const row = document.createElement("article");
    const title = document.createElement("p");
    title.textContent = `${song.title || "未命名"} · ${song.artist || ""}`;
    row.append(title);
    const button = (text, run) => {
      const b = document.createElement("button");
      b.textContent = text;
      b.onclick = () =>
        action(async () => {
          b.disabled = true;
          try {
            await run();
          } finally {
            b.disabled = false;
          }
        });
      row.append(b);
    };
    if (enqueue && song.status === "ready")
      button("手机试听", async () => {
        status("正在下载服务器音频…");
        await native.listen({ id });
        status("正在手机播放，可锁屏收听");
      });
    if (enqueue && song.status === "ready")
      button("点歌", async () => {
        await request(`/api/rooms/${config.room}/queue`, { song_id: id });
        await refresh();
        status("已加入队列");
      });
    button("屏蔽", async () => {
      await native.stop();
      blocked[config.server] = [
        ...new Set([...(blocked[config.server] || []), id]),
      ];
      localStorage.setItem("remote-blocked", JSON.stringify(blocked));
      row.remove();
      if ((snapshot?.now_playing?.song_id || snapshot?.now_playing?.id) === id)
        $("now").textContent = "当前内容已屏蔽";
      status("已在此设备屏蔽该内容");
    });
    button("举报并屏蔽", async () => {
      await native.stop();
      const reason = prompt("举报原因（不当内容、侵权或其他，最多 500 字）");
      if (!reason?.trim()) return;
      await request("/api/remote/reports", {
        song_id: id,
        reason: reason.trim().slice(0, 500),
      });
      blocked[config.server] = [
        ...new Set([...(blocked[config.server] || []), id]),
      ];
      localStorage.setItem("remote-blocked", JSON.stringify(blocked));
      row.remove();
      if ((snapshot?.now_playing?.song_id || snapshot?.now_playing?.id) === id)
        $("now").textContent = "当前内容已屏蔽";
      status("举报已送达服务器管理员，内容已在本机屏蔽");
    });
    root.append(row);
  }
  if (!root.children.length) root.textContent = "暂无可显示的歌曲";
}
async function search() {
  const epoch = generation;
  const data = await request(
    `/api/songs?q=${encodeURIComponent($("query").value.trim())}&page=${page}&count=20`,
  );
  if (epoch !== generation) return;
  render($("songs"), data.songs || [], true);
  $("more").hidden = page * 20 >= (data.total || 0);
}
$("connect").onsubmit = (event) => {
  event.preventDefault();
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
  page = 1;
  action(search);
};
$("more").onclick = () =>
  action(async () => {
    page++;
    await search();
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
    if (confirm("切换到下一首？")) {
      await request(`/api/rooms/${config.room}/skip`, {});
      await refresh();
    }
  });
$("volume").onchange = () =>
  action(async () => {
    if (!config) throw new Error("请先连接房间");
    await request(`/api/rooms/${config.room}/mix`, {
      volume: Number($("volume").value),
    });
  });
$("forget").onclick = () =>
  action(async () => {
    generation++;
    config = null;
    snapshot = null;
    blocked = {};
    localStorage.removeItem("remote-config");
    localStorage.removeItem("remote-blocked");
    await native.configure({ server: "" });
    $("server").value = "";
    $("room").value = "";
    $("api-key").value = "";
    $("songs").replaceChildren();
    $("queue").replaceChildren();
    $("now").textContent = "暂无播放";
    status("已清除本机数据");
    tab("settings");
  });
$("unblock").onclick = () => {
  blocked = {};
  localStorage.removeItem("remote-blocked");
  status("已清除屏蔽列表");
};
for (const button of document.querySelectorAll("[data-tab]"))
  button.onclick = () => tab(button.dataset.tab);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && config) action(refresh);
});
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
}
$("mode").onchange = connectionFields;
const saved = read("remote-config", null);
if (saved) {
  $("mode").value = saved.mode === "official" ? "official" : "self";
  $("server").value = saved.server;
  $("room").value = saved.room;
}

connectionFields();

$("stop-audio").onclick = () =>
  action(async () => {
    await native.stop();
    status("手机试听已停止");
  });
