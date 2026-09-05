import { t, bootI18n, onLangChange, applyDom } from "../../shared/i18n/js/i18n.js";
import { $ } from "../../shared/ui/js/dom.js";
import { fetchJson } from "../../shared/ui/js/http.js";

bootI18n();

let currentOwner = "";
let rechargeOwner = "";
let currentRoom = "";
let lastAccount = null;

function showError(text) {
  $("err").hidden = !text;
  $("err").textContent = text || "";
}

function fmtTime(ms) {
  if (!ms) return "";
  try {
    return new Date(Number(ms)).toLocaleString();
  } catch (_) {
    return String(ms);
  }
}

function labelUser(user, owner) {
  if (user && (user.username || user.sid)) {
    return (
      (user.username || user.sid) + (user.nickname && user.nickname !== user.username ? " · " + user.nickname : "")
    );
  }
  return owner || t("admin.guest");
}

function rowsHtml(headers, lines) {
  if (!lines.length) return `<p class="tiny">${t("admin.empty")}</p>`;
  return `<div class="table-wrap"><table class="admin"><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${lines.join("")}</tbody></table></div>`;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtBytes(value) {
  const n = Number(value || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function paintSongDebug(box, data) {
  if (!data.enabled) {
    box.innerHTML = `<p class="tiny">${t("admin.debugDisabled")}</p>`;
    return;
  }
  const trace = data.trace || {};
  const events = Array.isArray(trace.events) ? trace.events : [];
  const eventRows = events.length
    ? events
        .map(
          (item) =>
            `<li><span>${fmtTime(Number(item.at) * 1000)}</span><b>${esc(item.phase)}</b><em class="debug-${esc(item.status)}">${esc(item.status)}</em><code>${esc(
              Object.entries(item)
                .filter(([key]) => !["at", "phase", "status"].includes(key))
                .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`)
                .join(" · ")
            )}</code></li>`
        )
        .join("")
    : `<li class="tiny">${t("admin.debugEmpty")}</li>`;
  const files = (data.artifacts || [])
    .map((file) => `<span class="debug-file"><code>${esc(file.name)}</code> <em>${fmtBytes(file.size)}</em></span>`)
    .join("");
  const intermediates = (data.intermediates || [])
    .map(
      (item) =>
        `<details class="debug-intermediate"><summary>${esc(item.name)}</summary><pre>${esc(item.content)}</pre></details>`
    )
    .join("");
  box.innerHTML = `<div class="debug-summary"><b>${t("admin.debugStatus", { status: esc(trace.status || "未开始") })}</b>${trace.error ? `<span class="err">${esc(trace.error)}</span>` : ""}</div><ol class="debug-events">${eventRows}</ol>${files ? `<div class="debug-files"><span class="tiny">${t("admin.debugArtifacts")}</span>${files}</div>` : ""}${intermediates ? `<div class="debug-intermediates"><span class="tiny">${t("admin.debugArtifacts")}</span>${intermediates}</div>` : ""}`;
}

async function api(path, opts) {
  const hit = await fetchJson(path, opts);
  if (!hit.ok) {
    showError(hit.data.detail || t("api.admin_unauthorized"));
    if (hit.status === 401 || hit.status === 503) showGate(true);
  } else {
    showError("");
  }
  return hit;
}

function showGate(on) {
  $("gate").hidden = !on;
  $("desk").hidden = on;
}

function paintAccount(account) {
  lastAccount = account;
  currentOwner = account && account.owner ? account.owner : "";
  if (!account) {
    $("accountHint").hidden = false;
    $("accountHint").textContent = t("admin.noAccount");
    $("accountName").textContent = "";
    $("accountBal").textContent = "—";
    $("ledger").innerHTML = "";
    return;
  }
  $("accountHint").hidden = true;
  $("accountName").textContent =
    labelUser(account.user, account.owner) + (account.guest ? " · " + t("admin.guest") : "");
  $("accountBal").textContent = t("admin.balance", { n: account.balance });
  $("ledger").innerHTML = rowsHtml(
    [t("admin.ledger"), "", ""],
    (account.ledger || []).map((row) => {
      const cls = row.delta < 0 ? "delta-neg" : "delta-pos";
      const sign = row.delta > 0 ? "+" + row.delta : String(row.delta);
      return `<tr><td>${fmtTime(row.created_at)}</td><td>${row.kind}${row.ref ? " · " + row.ref : ""}</td><td class="${cls}">${sign}</td></tr>`;
    })
  );
}

function paintWallets(wallets) {
  $("wallets").innerHTML = rowsHtml(
    [t("admin.search"), t("admin.balance"), ""],
    (wallets || []).map((row) => {
      const name = labelUser(row.user, row.owner);
      return `<tr><td>${name}<div class="tiny">${row.owner}</div></td><td>${row.balance}</td><td><button type="button" class="btn" data-owner="${row.owner}">${t("admin.pick")}</button></td></tr>`;
    })
  );
  $("wallets")
    .querySelectorAll("[data-owner]")
    .forEach((btn) => {
      btn.onclick = () => loadPoints(btn.dataset.owner);
    });
}

async function loadSummary() {
  const { ok, data } = await api("/api/admin/summary");
  if (!ok) return false;
  $("summary").textContent = t("admin.rules", {
    queue: data.rules.queue_cost,
    process: data.rules.process_cost,
    ad: data.rules.ad_reward,
    sec: data.rules.ad_seconds,
    reg: data.rules.register_bonus,
    dl: data.rules.download_bonus
  });
  $("rules").textContent = $("summary").textContent;
  return true;
}

async function loadPoints(q) {
  const query = q || $("findQ").value.trim();
  const { ok, data } = await api("/api/admin/points?q=" + encodeURIComponent(query));
  if (!ok) return;
  paintWallets(data.wallets);
  if (data.account) paintAccount(data.account);
  else if (!query) paintAccount(null);
}

function paintRechargeAccount(account) {
  if (!account) {
    rechargeOwner = "";
    $("rechargeHint").hidden = false;
    $("rechargeName").textContent = "";
    $("rechargeBal").textContent = "—";
    return;
  }
  rechargeOwner = account.owner;
  $("rechargeHint").hidden = true;
  $("rechargeName").textContent = labelUser(account.user, account.owner);
  $("rechargeBal").textContent = t("admin.balance", { n: account.balance });
}

async function loadRecharges(q) {
  const query = q || $("rechargeQ").value.trim();
  const { ok, data } = await api("/api/admin/recharges?q=" + encodeURIComponent(query));
  if (!ok) return;
  if (data.account) paintRechargeAccount(data.account);
  else if (query) paintRechargeAccount(null);
  $("recharges").innerHTML = rowsHtml(
    [t("admin.tab.users"), t("admin.amount"), ""],
    (data.recharges || []).map((row) => {
      return `<tr><td>${labelUser(row.user, row.owner)}<div class="tiny">${fmtTime(row.created_at)}</div></td><td class="delta-pos">+${row.delta}</td><td>${row.ref || ""}</td></tr>`;
    })
  );
}

async function doRecharge(amount) {
  const n = Math.abs(Number(amount || $("rechargeAmt").value || 0));
  if (!rechargeOwner || !n) {
    showError(t("admin.noAccount"));
    return;
  }
  const { ok, data } = await api("/api/admin/recharge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      owner: rechargeOwner,
      amount: n,
      note: $("rechargeNote").value.trim()
    })
  });
  if (ok) {
    paintRechargeAccount(data);
    loadRecharges("");
  }
}

async function loadUsers() {
  const q = $("userQ") ? $("userQ").value.trim() : "";
  const { ok, data } = await api("/api/admin/users?q=" + encodeURIComponent(q));
  if (!ok) return;
  $("users").innerHTML = rowsHtml(
    [t("admin.tab.users"), t("admin.balance"), ""],
    (data.users || []).map((user) => {
      return `<tr>
        <td>${labelUser(user, user.owner)}<div class="tiny">${user.username || ""} · ${user.owner}</div></td>
        <td>${user.balance}</td>
        <td>
          <button type="button" class="btn" data-charge="${user.owner}">${t("admin.recharge")}</button>
          <button type="button" class="btn" data-cut="${user.owner}">${t("admin.cut")}</button>
        </td>
      </tr>`;
    })
  );
  $("users")
    .querySelectorAll("[data-charge]")
    .forEach((btn) => {
      btn.onclick = () => {
        showTab("recharge");
        $("rechargeQ").value = btn.dataset.charge;
        loadRecharges(btn.dataset.charge);
      };
    });
  $("users")
    .querySelectorAll("[data-cut]")
    .forEach((btn) => {
      btn.onclick = () => {
        showTab("points");
        $("findQ").value = btn.dataset.cut;
        loadPoints(btn.dataset.cut);
      };
    });
}

async function loadSongs() {
  const q = $("songQ") ? $("songQ").value.trim() : "";
  const { ok, data } = await api("/api/admin/songs?q=" + encodeURIComponent(q));
  if (!ok) return;
  $("songs").innerHTML = rowsHtml(
    [t("admin.tab.songs"), "", ""],
    (data.songs || []).map((song) => {
      const retry = song.status === "failed" || (song.status === "ready" && song.error) ? `<button type="button" class="btn" data-retry="${song.id}">${t("admin.retry")}</button>` : "";
      const songId = encodeURIComponent(song.id);
      return `<tr>
        <td>
          <input data-title="${esc(song.id)}" value="${esc(song.title || "")}" />
          <div class="tiny">${esc(song.status || "")} · ${esc(song.id)}</div>
          <p class="song-links"><a href="/m.html?song=${songId}#lyrics" target="_blank" rel="noopener">${t("admin.songLyrics")}</a><a href="/m.html?song=${songId}#player" target="_blank" rel="noopener">${t("admin.songListen")}</a><button type="button" class="btn ghost" data-debug="${esc(song.id)}">${t("admin.songDebug")}</button></p>
          <div class="song-debug" data-debug-box="${esc(song.id)}" hidden></div>
        </td>
        <td><input data-artist="${esc(song.id)}" value="${esc(song.artist || "")}" /></td>
        <td>
          <button type="button" class="btn" data-save="${song.id}">${t("admin.saveSong")}</button>
          ${retry}
          <button type="button" class="btn danger" data-del="${song.id}">${t("admin.delete")}</button>
        </td>
      </tr>`;
    })
  );
  $("songs")
    .querySelectorAll("[data-debug]")
    .forEach((btn) => {
      btn.onclick = async () => {
        const box = [...$("songs").querySelectorAll("[data-debug-box]")].find(
          (item) => item.dataset.debugBox === btn.dataset.debug
        );
        if (!box) return;
        box.hidden = !box.hidden;
        if (box.hidden) return;
        box.innerHTML = `<p class="tiny">${t("admin.debugLoading")}</p>`;
        const { ok, data } = await api("/api/admin/songs/" + encodeURIComponent(btn.dataset.debug) + "/debug");
        if (ok) paintSongDebug(box, data);
      };
    });
  $("songs")
    .querySelectorAll("[data-del]")
    .forEach((btn) => {
      btn.onclick = async () => {
        await api("/api/admin/songs/" + btn.dataset.del, { method: "DELETE" });
        loadSongs();
      };
    });
  $("songs")
    .querySelectorAll("[data-retry]")
    .forEach((btn) => {
      btn.onclick = async () => {
        await api("/api/admin/songs/" + btn.dataset.retry + "/retry", { method: "POST" });
        loadSongs();
      };
    });
  $("songs")
    .querySelectorAll("[data-save]")
    .forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.dataset.save;
        const title = $("songs").querySelector(`[data-title="${id}"]`);
        const artist = $("songs").querySelector(`[data-artist="${id}"]`);
        await api("/api/admin/songs/" + id, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title ? title.value : "",
            artist: artist ? artist.value : ""
          })
        });
        loadSongs();
      };
    });
}

function paintRoomDetail(room) {
  if (!room || !room.code) {
    currentRoom = "";
    $("roomDetail").hidden = true;
    return;
  }
  currentRoom = room.code;
  $("roomDetail").hidden = false;
  $("roomDetailName").textContent = room.code;
  const now = room.now_playing || {};
  $("roomDetailMeta").textContent = t("admin.roomMeta", {
    n: (room.queue || []).length,
    title: now.title || t("admin.empty")
  });
  $("roomQueue").innerHTML = rowsHtml(
    [t("admin.tab.songs"), "", ""],
    (room.queue || []).map((item, idx) => {
      const on = room.now_index === idx ? " · now" : "";
      return `<tr>
        <td>${item.title || item.song_id}${on}<div class="tiny">${item.artist || ""} · ${item.status || ""}</div></td>
        <td>
          <button type="button" class="btn" data-play="${item.id}">${t("admin.playNow")}</button>
          <button type="button" class="btn" data-bump="${item.id}">${t("admin.bump")}</button>
        </td>
        <td><button type="button" class="btn danger" data-drop="${item.id}">${t("admin.removeItem")}</button></td>
      </tr>`;
    })
  );
  $("roomQueue")
    .querySelectorAll("[data-play]")
    .forEach((btn) => {
      btn.onclick = async () => {
        const { ok, data } = await api("/api/admin/rooms/" + currentRoom + "/play", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: btn.dataset.play })
        });
        if (ok) paintRoomDetail(data);
        loadRooms();
      };
    });
  $("roomQueue")
    .querySelectorAll("[data-bump]")
    .forEach((btn) => {
      btn.onclick = async () => {
        const { ok, data } = await api("/api/admin/rooms/" + currentRoom + "/bump", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: btn.dataset.bump })
        });
        if (ok) paintRoomDetail(data);
        loadRooms();
      };
    });
  $("roomQueue")
    .querySelectorAll("[data-drop]")
    .forEach((btn) => {
      btn.onclick = async () => {
        const { ok, data } = await api("/api/admin/rooms/" + currentRoom + "/queue/" + btn.dataset.drop, {
          method: "DELETE"
        });
        if (ok) paintRoomDetail(data);
        loadRooms();
      };
    });
}

async function openRoom(code) {
  const { ok, data } = await api("/api/admin/rooms/" + code);
  if (ok) paintRoomDetail(data);
}

async function loadRooms() {
  const q = $("roomQ") ? $("roomQ").value.trim() : "";
  const { ok, data } = await api("/api/admin/rooms?q=" + encodeURIComponent(q));
  if (!ok) return;
  $("rooms").innerHTML = rowsHtml(
    [t("admin.tab.rooms"), "", ""],
    (data.rooms || []).map((room) => {
      return `<tr>
        <td>${room.code}<div class="tiny">${room.now_title || t("admin.empty")} · ${room.queue_n || 0}</div></td>
        <td><button type="button" class="btn" data-open="${room.code}">${t("admin.pick")}</button></td>
        <td>
          <button type="button" class="btn" data-skip="${room.code}">${t("admin.skip")}</button>
          <button type="button" class="btn danger" data-delroom="${room.code}">${t("admin.deleteRoom")}</button>
        </td>
      </tr>`;
    })
  );
  $("rooms")
    .querySelectorAll("[data-open]")
    .forEach((btn) => {
      btn.onclick = () => openRoom(btn.dataset.open);
    });
  $("rooms")
    .querySelectorAll("[data-skip]")
    .forEach((btn) => {
      btn.onclick = async () => {
        await api("/api/admin/rooms/" + btn.dataset.skip + "/skip", { method: "POST" });
        loadRooms();
        if (currentRoom === btn.dataset.skip) openRoom(currentRoom);
      };
    });
  $("rooms")
    .querySelectorAll("[data-delroom]")
    .forEach((btn) => {
      btn.onclick = async () => {
        await api("/api/admin/rooms/" + btn.dataset.delroom, { method: "DELETE" });
        if (currentRoom === btn.dataset.delroom) paintRoomDetail(null);
        loadRooms();
      };
    });
}

async function loadAds() {
  const { ok, data } = await api("/api/admin/ads");
  if (!ok) return;
  $("ads").innerHTML = rowsHtml(
    [t("admin.tab.ads"), ""],
    (data.ads || []).map((ad) => {
      return `<tr><td>${ad.title || ad.id}<div class="tiny">${ad.body || ""}</div></td><td><a href="${ad.url || "#"}">${ad.cta || ""}</a></td></tr>`;
    })
  );
}

async function loadSettings() {
  const { ok, data } = await api("/api/admin/settings");
  if (!ok) return;
  $("settings").innerHTML = (data.settings || [])
    .map((item) => {
      const checked = item.type === "bool" ? (item.value ? " checked" : "") : "";
      if (item.type === "bool")
        return `<label class="field"><span class="tiny">${item.label} <em class="tiny">(${item.source})</em></span><input type="checkbox" data-setting="${item.key}"${checked}></label>`;
      const type = item.secret ? "password" : "text";
      const value = item.secret
        ? ""
        : String(item.value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/"/g, "&quot;");
      const placeholder = item.secret && item.value ? "已配置，留空保持不变" : "";
      return `<label class="field"><span class="tiny">${item.label} <em class="tiny">(${item.source})</em></span><input type="${type}" data-setting="${item.key}" value="${value}" placeholder="${placeholder}"></label>`;
    })
    .join("");
}

$("settingsForm").onsubmit = async (event) => {
  event.preventDefault();
  const values = {};
  $("settings")
    .querySelectorAll("[data-setting]")
    .forEach((el) => {
      if (el.type === "password" && !el.value) return;
      values[el.dataset.setting] = el.type === "checkbox" ? el.checked : el.value;
    });
  await api("/api/admin/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings: values })
  });
  loadSummary();
  loadSettings();
};

function showTab(name) {
  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.tab === name);
  });
  ["recharge", "points", "users", "songs", "rooms", "ads", "settings"].forEach((key) => {
    const pane = $(`pane-${key}`);
    if (pane) pane.hidden = key !== name;
  });
  if (name === "recharge") loadRecharges($("rechargeQ").value.trim());
  if (name === "users") loadUsers();
  if (name === "songs") loadSongs();
  if (name === "rooms") loadRooms();
  if (name === "ads") loadAds();
  if (name === "settings") loadSettings();
  if (name === "points") loadPoints($("findQ").value.trim());
}

async function bootDesk() {
  const ok = await loadSummary();
  if (!ok) return;
  showGate(false);
  showTab("recharge");
}

async function adjust(sign) {
  const amount = Math.abs(Number($("amount").value || 0));
  if (!currentOwner || !amount) {
    showError(t("admin.noAccount"));
    return;
  }
  const { ok, data } = await api("/api/admin/points", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      owner: currentOwner,
      delta: sign * amount,
      note: $("note").value.trim()
    })
  });
  if (ok) {
    paintAccount(data);
    loadPoints("");
  }
}

onLangChange(() => {
  applyDom();
  if (lastAccount) paintAccount(lastAccount);
});

$("gate").onsubmit = async (event) => {
  event.preventDefault();
  showError("");
  const { ok, data } = await fetchJson("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: $("token").value })
  });
  if (!ok) {
    showError(data.detail || t("api.admin_unauthorized"));
    return;
  }
  $("token").value = "";
  bootDesk();
};

$("logout").onclick = async () => {
  await fetchJson("/api/admin/logout", { method: "POST" });
  currentOwner = "";
  lastAccount = null;
  showGate(true);
};

$("findForm").onsubmit = (event) => {
  event.preventDefault();
  loadPoints($("findQ").value.trim());
};

$("addPts").onclick = () => adjust(1);
$("cutPts").onclick = () => adjust(-1);

$("rechargeFind").onsubmit = (event) => {
  event.preventDefault();
  loadRecharges($("rechargeQ").value.trim());
};
$("rechargePacks").onclick = (event) => {
  const btn = event.target.closest("[data-pack]");
  if (!btn) return;
  $("rechargeAmt").value = btn.dataset.pack;
  doRecharge(btn.dataset.pack);
};
$("doRecharge").onclick = () => doRecharge();

$("createUser").onsubmit = async (event) => {
  event.preventDefault();
  const { ok, data } = await api("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: $("newUser").value.trim(),
      password: $("newPass").value,
      nickname: $("newNick").value.trim()
    })
  });
  if (!ok) return;
  $("newUser").value = "";
  $("newPass").value = "";
  $("newNick").value = "";
  loadUsers();
  showTab("recharge");
  $("rechargeQ").value = data.username || data.owner;
  loadRecharges(data.username || data.owner);
};
$("userFind").onsubmit = (event) => {
  event.preventDefault();
  loadUsers();
};

$("importSong").onsubmit = async (event) => {
  event.preventDefault();
  const { ok } = await api("/api/admin/songs/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: $("songQuery").value.trim(),
      title: $("songQuery").value.trim(),
      artist: $("songArtist").value.trim()
    })
  });
  if (ok) {
    $("songQuery").value = "";
    $("songArtist").value = "";
    loadSongs();
  }
};
$("songFind").onsubmit = (event) => {
  event.preventDefault();
  loadSongs();
};

$("createRoom").onsubmit = async (event) => {
  event.preventDefault();
  const { ok, data } = await api("/api/admin/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: $("newRoom").value.trim() })
  });
  if (!ok) return;
  $("newRoom").value = "";
  loadRooms();
  paintRoomDetail(data);
};
$("roomFind").onsubmit = (event) => {
  event.preventDefault();
  loadRooms();
};
$("roomEnqueue").onsubmit = async (event) => {
  event.preventDefault();
  if (!currentRoom) return;
  const { ok, data } = await api("/api/admin/rooms/" + currentRoom + "/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ song_id: $("roomSongId").value.trim() })
  });
  if (ok) {
    $("roomSongId").value = "";
    paintRoomDetail(data);
    loadRooms();
  }
};
$("roomSkip").onclick = async () => {
  if (!currentRoom) return;
  const { ok, data } = await api("/api/admin/rooms/" + currentRoom + "/skip", { method: "POST" });
  if (ok) paintRoomDetail(data);
  loadRooms();
};
$("roomClear").onclick = async () => {
  if (!currentRoom) return;
  const { ok, data } = await api("/api/admin/rooms/" + currentRoom + "/clear", { method: "POST" });
  if (ok) paintRoomDetail(data);
  loadRooms();
};
$("roomDelete").onclick = async () => {
  if (!currentRoom) return;
  const code = currentRoom;
  const { ok } = await api("/api/admin/rooms/" + code, { method: "DELETE" });
  if (ok) {
    paintRoomDetail(null);
    loadRooms();
  }
};

$("tabs").onclick = (event) => {
  const btn = event.target.closest("[data-tab]");
  if (btn) showTab(btn.dataset.tab);
};

(async function boot() {
  const { ok } = await fetchJson("/api/admin/me");
  if (ok) bootDesk();
  else showGate(true);
})();
