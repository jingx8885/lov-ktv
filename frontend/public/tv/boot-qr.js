(function () {
  if (window.__lovktvQrBooted) return;

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function savedCode() {
    try {
      var raw = String(localStorage.getItem("tvRoom") || "").toUpperCase();
      if (/^[A-Z0-9]{4,12}$/.test(raw)) return raw;
    } catch (err) {}
    return "";
  }

  function remember(code) {
    if (!code) return;
    try { localStorage.setItem("tvRoom", code); } catch (err) {}
  }

  function drawCanvas(box, url) {
    var qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    var n = qr.getModuleCount();
    var scale = Math.max(3, Math.floor(140 / n));
    var canvas = document.createElement("canvas");
    canvas.width = n * scale;
    canvas.height = n * scale;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#000000";
    var r, c;
    for (r = 0; r < n; r++) {
      for (c = 0; c < n; c++) {
        if (qr.isDark(r, c)) ctx.fillRect(c * scale, r * scale, scale, scale);
      }
    }
    box.innerHTML = "";
    box.appendChild(canvas);
  }

  function paint(url, code) {
    window.__lovktvQrBooted = true;
    remember(code);
    setText("code", code || "");
    var link = document.getElementById("phoneLink");
    if (link && url) link.href = url;
    var hint = document.getElementById("remoteHint");
    if (hint) hint.hidden = false;
    var box = document.getElementById("qr");
    if (!box) return;
    box.innerHTML = "";
    if (typeof qrcode === "function" && url) {
      try {
        drawCanvas(box, url);
        return;
      } catch (err) {}
      try {
        var qr = qrcode(0, "M");
        qr.addData(url);
        qr.make();
        box.innerHTML = qr.createImgTag(4, 0);
        return;
      } catch (err2) {}
    }
    box.textContent = url || "";
  }

  function json(res) {
    return res.json();
  }

  function openRoom() {
    var saved = savedCode();
    return fetch("/api/host").then(json).then(function (host) {
      var fromHost = host && host.room ? String(host.room).toUpperCase() : "";
      if (/^[A-Z0-9]{4,12}$/.test(fromHost)) {
        return { host: host, code: fromHost };
      }
      var body = saved ? JSON.stringify({ code: saved }) : "{}";
      return fetch("/api/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
      }).then(json).then(function (room) {
        return { host: host, code: (room && room.code) || "" };
      });
    });
  }

  function boot() {
    if (/\bandroidtv=1\b/.test(location.search || "") || /LovKtvAndroidTV/i.test(navigator.userAgent || "")) {
      document.body.classList.add("androidtv");
    }
    openRoom()
      .then(function (hit) {
        var code = (hit && hit.code) || "";
        if (!code) throw new Error("开房失败");
        remember(code);
        var host = (hit && hit.host) || {};
        var process = (host.process_origin || "").replace(/\/$/, "");
        var origin = (host.origin || location.origin || "").replace(/\/$/, "");
        var url = (process || origin) + "/m.html?room=" + code + "&v=queue3";
        if (origin && process && origin !== process) {
          url += "&lan=" + encodeURIComponent(origin);
        }
        paint(url, code);
      })
      .catch(function (err) {
        setText("code", "开房失败");
        var box = document.getElementById("qr");
        if (box) box.textContent = (err && err.message) || "请按菜单键检查处理服务器";
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
