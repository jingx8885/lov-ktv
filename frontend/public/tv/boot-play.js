(function () {
  if (window.__lovktvPlayBooted) return;
  function isAndroidTv() {
    return /\bandroidtv=1\b/.test(location.search || "") || /LovKtvAndroidTV/i.test(navigator.userAgent || "");
  }
  if (!isAndroidTv()) return;

  var room = null;
  var lastItem = "";
  var lyrics = { cues: [] };

  function $(id) {
    return document.getElementById(id);
  }

  function playEl(el) {
    if (!el) return;
    var p = el.play();
    if (p && p.catch) p.catch(function () {});
  }

  function roomCode() {
    var el = $("code");
    var text = el ? String(el.textContent || "").trim().toUpperCase() : "";
    if (text && text.indexOf("失败") < 0 && text.indexOf("…") < 0 && /^[A-Z0-9]{4,12}$/.test(text)) {
      return text;
    }
    try {
      return String(localStorage.getItem("tvRoom") || "").toUpperCase();
    } catch (err) {
      return "";
    }
  }

  function jsonFetch(url, opts) {
    return fetch(url, opts || {}).then(function (res) {
      return res.json().then(function (data) {
        return { ok: res.ok, data: data };
      }).catch(function () {
        return { ok: res.ok, data: {} };
      });
    });
  }

  function mediaUrl(songId, name) {
    var q = "";
    if (name === "karaoke.m4a" || name === "guide.m4a") q = "?v=stem2";
    if (name === "lyrics.json") q = "?v=ja-kanji";
    return "/media/" + songId + "/" + name + q;
  }

  function hideGate() {
    var gate = $("gate");
    if (gate) gate.hidden = true;
  }

  function applyMix() {
    var karaoke = $("karaoke");
    var vocal = $("vocal");
    if (!karaoke) return;
    var mix = room && room.vocal_mix != null ? Number(room.vocal_mix) : 1;
    var vol = room && room.volume != null ? Number(room.volume) / 100 : 0.8;
    karaoke.muted = mix >= 0.99;
    karaoke.volume = karaoke.muted ? 0 : vol * (1 - mix);
    if (vocal) {
      vocal.muted = mix <= 0.01;
      vocal.volume = vocal.muted ? 0 : vol * mix;
    }
  }

  function bindMtv(songId) {
    var mtv = $("mtv");
    if (!mtv || !songId) return;
    mtv.muted = true;
    mtv.defaultMuted = true;
    mtv.volume = 0;
    mtv.onerror = function () {
      mtv.hidden = true;
      document.body.classList.remove("has-mtv");
    };
    mtv.onloadeddata = function () {
      mtv.muted = true;
      mtv.hidden = false;
      document.body.classList.add("has-mtv");
      playEl(mtv);
    };
    mtv.src = mediaUrl(songId, "mtv.mp4");
  }

  function startSong(now) {
    var songId = now && now.song_id;
    var karaoke = $("karaoke");
    var vocal = $("vocal");
    if (!karaoke || !songId) return;
    hideGate();
    karaoke.src = mediaUrl(songId, "karaoke.m4a");
    karaoke.onerror = function () {
      karaoke.src = mediaUrl(songId, "original.mp3");
    };
    if (vocal) {
      vocal.src = mediaUrl(songId, "original.mp3");
      vocal.onerror = function () {
        vocal.src = mediaUrl(songId, "guide.m4a");
      };
    }
    applyMix();
    bindMtv(songId);
    playEl(karaoke);
    playEl(vocal);
    playEl($("mtv"));
    jsonFetch(mediaUrl(songId, "lyrics.json") + "&t=" + Date.now()).then(function (hit) {
      lyrics = hit.ok && hit.data ? hit.data : { cues: [] };
      return jsonFetch("/media/" + songId + "/skeleton.json");
    }).then(function (skel) {
      if (skel && skel.ok && skel.data && skel.data.has_video) lyrics.has_video = true;
      syncLyricSkin();
    }).catch(function () {
      lyrics = lyrics || { cues: [] };
      syncLyricSkin();
    });
    karaoke.onended = function () {
      skip();
    };
  }

  function stopSong() {
    ["karaoke", "vocal", "mtv"].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.pause();
      el.removeAttribute("src");
      try { el.load(); } catch (err) {}
    });
    var mtv = $("mtv");
    if (mtv) mtv.hidden = true;
    document.body.classList.remove("has-mtv", "has-native-mv");
    lyrics = { cues: [] };
    var cur = $("cur");
    var prev = $("prev");
    var next = $("next");
    if (cur) cur.textContent = "";
    if (prev) prev.textContent = "";
    if (next) next.textContent = "";
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function cueHtml(cue) {
    if (!cue) return "";
    var tokens = cue.tokens || [];
    var i;
    var tok;
    var body;
    var roma;
    var gloss;
    var reading;
    var parts;
    if (!tokens.length) {
      body = '<span class="rb"><span class="rb-base">' + esc(cue.text || "") + '</span><span class="rb-fill" style="width:0">' + esc(cue.text || "") + "</span></span>";
      if (cue.zh) body += '<span class="lyric-zh">' + esc(cue.zh) + "</span>";
      return body;
    }
    parts = ['<span class="line-words">'];
    for (i = 0; i < tokens.length; i++) {
      tok = tokens[i] || {};
      reading = tok.reading && tok.reading !== tok.text ? String(tok.reading) : "";
      body = '<span class="rb"><span class="rb-base">' + esc(tok.text || "") + '</span><span class="rb-fill" style="width:0">' + esc(tok.text || "") + "</span></span>";
      roma = tok.romaji && tok.romaji !== tok.text ? '<span class="roma">' + esc(tok.romaji) + "</span>" : "";
      gloss = tok.zh ? '<span class="gloss">' + esc(tok.zh) + "</span>" : "";
      if (reading) {
        reading = '<span class="rt"><i>' + esc(reading).split("").join("</i><i>") + "</i></span>";
      } else {
        reading = "";
      }
      parts.push('<span class="tok"><span class="anno">' + reading + body + roma + gloss + "</span></span>");
    }
    parts.push("</span>");
    if (cue.zh) parts.push('<span class="lyric-zh">' + esc(cue.zh) + "</span>");
    return parts.join("");
  }

  function setLine(el, cue) {
    if (!el) return;
    var html = cueHtml(cue);
    if (el.getAttribute("data-html") === html) return;
    el.setAttribute("data-html", html);
    el.innerHTML = html;
  }

  function syncLyricSkin() {
    var body = document.body;
    if (!body) return;
    body.setAttribute("data-lyric-mode", "all");
    var native = !!(lyrics && (lyrics.native_video === true || lyrics.has_video === true));
    if (native) body.classList.add("has-native-mv");
    else body.classList.remove("has-native-mv");
  }

  function tokenP(tok, t) {
    if (!tok) return 0;
    if (t < 0) return 0;
    if (t >= tok.end_ms) return 100;
    if (t >= tok.start_ms) return ((t - tok.start_ms) / Math.max(tok.end_ms - tok.start_ms, 1)) * 100;
    return 0;
  }

  function fillLine(el, cue, t) {
    if (!el || !cue) return;
    var nodes = el.querySelectorAll(".rb-fill");
    var toks = cue.tokens || [];
    var i;
    if (!nodes.length) return;
    if (!toks.length) {
      nodes[0].style.width = Math.round(tokenP(cue, t)) + "%";
      return;
    }
    for (i = 0; i < nodes.length; i++) {
      nodes[i].style.width = Math.round(tokenP(toks[i] || cue, t)) + "%";
    }
  }

  function paintLyrics() {
    if (window.LovKtvRemote && window.LovKtvRemote.__module) return;
    var karaoke = $("karaoke");
    var cues = (lyrics && lyrics.cues) || [];
    if (!karaoke || !cues.length) return;
    syncLyricSkin();
    var t = Math.floor((karaoke.currentTime || 0) * 1000);
    var i;
    var idx = -1;
    for (i = 0; i < cues.length; i++) {
      if (t >= cues[i].start_ms && t < cues[i].end_ms) {
        idx = i;
        break;
      }
    }
    var cue = idx >= 0 ? cues[idx] : null;
    setLine($("prev"), idx > 0 ? cues[idx - 1] : null);
    setLine($("cur"), cue);
    setLine($("next"), idx >= 0 && idx + 1 < cues.length ? cues[idx + 1] : null);
    fillLine($("prev"), idx > 0 ? cues[idx - 1] : null, 1e12);
    fillLine($("cur"), cue, t);
    fillLine($("next"), idx >= 0 && idx + 1 < cues.length ? cues[idx + 1] : null, -1);
    var mtv = $("mtv");
    if (mtv && karaoke && !karaoke.paused && mtv.src && mtv.paused) playEl(mtv);
  }

  function tick() {
    var c = roomCode();
    if (!c) return;
    jsonFetch("/api/rooms/" + c).then(function (hit) {
      if (!hit.ok || !hit.data || !hit.data.code) return;
      room = hit.data;
      try { localStorage.setItem("tvRoom", room.code); } catch (err) {}
      var now = room.now_playing;
      var title = $("title");
      var meta = $("meta");
      if (!now) {
        if (title) title.textContent = "等待点歌";
        if (meta) meta.textContent = "";
        if (lastItem) {
          stopSong();
          lastItem = "";
        }
        return;
      }
      if (title) title.textContent = now.title || "";
      if (meta) meta.textContent = (now.artist || "") + " · " + (now.status || "");
      if (now.status !== "ready") return;
      var key = now.id || now.song_id;
      if (lastItem !== key) {
        lastItem = key;
        startSong(now);
      } else {
        applyMix();
        var karaoke = $("karaoke");
        if (karaoke && karaoke.paused && karaoke.getAttribute("src")) playEl(karaoke);
      }
    }).catch(function () {});
  }

  function postAction(path, body) {
    var c = roomCode();
    if (!c) return;
    jsonFetch("/api/rooms/" + c + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(function (hit) {
      if (hit.ok && hit.data && hit.data.code) {
        room = hit.data;
        lastItem = "";
        tick();
      }
    }).catch(function () {});
  }

  function skip() {
    postAction("/skip", {});
  }

  function toggleVocal() {
    var next = room && Number(room.vocal_mix || 0) > 0.5 ? 0 : 1;
    postAction("/mix", { vocal_mix: next });
  }

  function nudgeVol(delta) {
    var cur = room && room.volume != null ? Number(room.volume) : 80;
    var next = Math.max(0, Math.min(100, cur + Number(delta || 0)));
    postAction("/mix", { volume: next });
  }

  function confirm() {
    hideGate();
    var karaoke = $("karaoke");
    if (karaoke && karaoke.paused) playEl(karaoke);
    else toggleVocal();
  }

  function karaokeHasSrc() {
    var k = $("karaoke");
    return !!(k && k.getAttribute("src"));
  }

  function startClassic(force) {
    if (window.LovKtvRemote && window.LovKtvRemote.__module) return;
    if (window.__lovktvPlayBooted) {
      if (force) tick();
      return;
    }
    window.__lovktvPlayBooted = true;
    window.LovKtvRemote = {
      skip: skip,
      toggleVocal: toggleVocal,
      volumeUp: function () { nudgeVol(10); },
      volumeDown: function () { nudgeVol(-10); },
      confirm: confirm,
      start: function () {
        hideGate();
        var karaoke = $("karaoke");
        if (karaoke) playEl(karaoke);
      },
    };
    var startBtn = $("start");
    if (startBtn) {
      startBtn.onclick = function () {
        hideGate();
        confirm();
      };
    }
    hideGate();
    tick();
    setInterval(tick, 1500);
    setInterval(paintLyrics, 200);
  }

  function boot() {
    setTimeout(function () {
      if (window.LovKtvRemote && window.LovKtvRemote.__module) return;
      startClassic(true);
    }, 2500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
