(function () {
  if (window.__lovktvPlayBooted) return;
  function isAndroidTv() {
    return /\bandroidtv=1\b/.test(location.search || "") || /LovKtvAndroidTV/i.test(navigator.userAgent || "");
  }
  if (!isAndroidTv()) return;

  var room = null;
  var lastItem = "";
  var lyrics = { cues: [] };
  var lastNativeLyric = "";
  var lastNativeSeek = 0;

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
    var now = room && room.now_playing;
    var rev = now && now.song_id === songId && now.media_rev ? String(now.media_rev) : "";
    return "/media/" + songId + "/" + name + (rev ? "?v=" + encodeURIComponent(rev) : "");
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

  function hasNativePlayer() {
    return !!(window.LovKtvNative && typeof window.LovKtvNative.playMtv === "function");
  }

  function bindMtv(songId) {
    var mtv = $("mtv");
    var htmlSrc = mediaUrl(songId, "mtv.mp4");
    var cover = mediaUrl(songId, "cover.jpg");
    if (!songId) return;
    if (hasNativePlayer()) {
      document.body.classList.add("has-mtv", "has-native-player");
      if (document.documentElement) {
        document.documentElement.style.background = "transparent";
        document.documentElement.style.backgroundColor = "transparent";
      }
      document.body.style.background = "transparent";
      document.body.style.backgroundColor = "transparent";
      if (mtv) {
        mtv.hidden = true;
        mtv.pause();
        mtv.removeAttribute("src");
      }
      try { window.LovKtvNative.playMtv((location.origin || "") + htmlSrc); } catch (err2) {}
      return;
    }
    if (!mtv) return;
    mtv.muted = true;
    mtv.defaultMuted = true;
    mtv.volume = 0;
    mtv.onerror = function () {
      document.body.classList.add("has-mtv-cover");
      document.body.style.backgroundImage = "url(" + cover + ")";
      mtv.hidden = true;
      document.body.classList.remove("has-mtv");
    };
    mtv.onloadeddata = function () {
      mtv.muted = true;
      mtv.hidden = false;
      document.body.classList.add("has-mtv");
      document.body.classList.remove("has-mtv-cover");
      document.body.style.backgroundImage = "";
      playEl(mtv);
    };
    mtv.src = htmlSrc;
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
    if (vocal && !vocal.muted) playEl(vocal);
    var mtv = $("mtv");
    if (mtv && !hasNativePlayer()) {
      mtv.muted = true;
      mtv.volume = 0;
      playEl(mtv);
    } else if (mtv) {
      mtv.pause();
      mtv.removeAttribute("src");
    }
    jsonFetch(mediaUrl(songId, "lyrics.json")).then(function (hit) {
      lyrics = hit.ok && hit.data ? hit.data : { cues: [] };
      return jsonFetch(mediaUrl(songId, "skeleton.json"));
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
    document.body.classList.remove("has-mtv", "has-native-mv", "has-native-player", "has-mtv-cover");
    document.body.style.backgroundImage = "";
    document.body.style.background = "";
    document.body.style.backgroundColor = "";
    if (document.documentElement) {
      document.documentElement.style.background = "";
      document.documentElement.style.backgroundColor = "";
    }
    lyrics = { cues: [] };
    lastNativeLyric = "";
    try {
      if (window.LovKtvNative) {
        if (window.LovKtvNative.stopMtv) window.LovKtvNative.stopMtv();
        if (window.LovKtvNative.clearLyrics) window.LovKtvNative.clearLyrics();
      }
    } catch (err2) {}
    var cur = $("cur");
    var prev = $("prev");
    var next = $("next");
    if (cur) { cur.innerHTML = ""; cur.removeAttribute("data-html"); }
    if (prev) { prev.innerHTML = ""; prev.removeAttribute("data-html"); }
    if (next) { next.innerHTML = ""; next.removeAttribute("data-html"); }
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
      roma = tok.romaji && tok.romaji !== tok.text ? tok.romaji : "";
      if (!roma && tok.reading && /^[A-Za-z0-9']/.test(String(tok.reading)) && tok.reading !== tok.text) {
        roma = String(tok.reading);
      }
      roma = '<span class="roma">' + esc(roma) + "</span>";
      var glossText = String(tok.zh || "").trim();
      var tokText = String(tok.text || "").trim();
      if (!tokText || /^[ー\-–~～、。！!？?…・·（）()「」『』【】\[\].,'"“”]$/.test(tokText) || /^(长音|促音|浊点|半浊点|！|!)$/.test(glossText)) {
        glossText = "";
      }
      gloss = '<span class="gloss">' + esc(glossText) + "</span>";
      if (reading) {
        reading = '<span class="rt"><i>' + esc(reading).split("").join("</i><i>") + "</i></span>";
      } else {
        reading = '<span class="rt"></span>';
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

  function hideNativeLyrics() {
    if (!window.LovKtvNative || typeof window.LovKtvNative.clearLyrics !== "function") return;
    if (!lastNativeLyric) return;
    lastNativeLyric = "";
    try { window.LovKtvNative.clearLyrics(); } catch (err) {}
  }

  function syncNativeVideo(karaoke) {
    var native = window.LovKtvNative;
    var t;
    var pos;
    var target;
    var mtvDur;
    var karaokeDur;
    var extra;
    if (!native || !karaoke) return;
    try {
      if (karaoke.paused && native.pauseMtv) native.pauseMtv();
      else if (!karaoke.paused && karaoke.currentTime > 0.05 && native.resumeMtv) native.resumeMtv();
      if (karaoke.paused || typeof native.positionMs !== "function" || typeof native.seekMtv !== "function") return;
      t = Math.floor((karaoke.currentTime || 0) * 1000);
      karaokeDur = isFinite(karaoke.duration) ? Math.round(karaoke.duration * 1000) : 0;
      mtvDur = typeof native.durationMs === "function" ? Number(native.durationMs()) || 0 : 0;
      extra = mtvDur - karaokeDur;
      target = t + (extra >= 1500 && extra <= 30000 ? extra : 0);
      pos = Number(native.positionMs()) || 0;
      if (Math.abs(pos - target) > 120 && Date.now() - lastNativeSeek > 400) {
        lastNativeSeek = Date.now();
        native.seekMtv(target);
      }
    } catch (err) {}
  }

  function paintLyrics() {
    if (moduleOwnsPlayback()) return;
    var karaoke = $("karaoke");
    var cues = (lyrics && lyrics.cues) || [];
    var t;
    var i;
    var idx = -1;
    var upcoming = -1;
    var cue;
    var held;
    if (!karaoke) return;
    syncLyricSkin();
    t = Math.floor((karaoke.currentTime || 0) * 1000);
    for (i = 0; i < cues.length; i++) {
      if (t >= cues[i].start_ms && t < cues[i].end_ms) {
        idx = i;
        break;
      }
      if (upcoming < 0 && t < cues[i].start_ms) upcoming = i;
    }
    if (idx >= 0) {
      cue = cues[idx];
      setLine($("prev"), idx > 0 ? cues[idx - 1] : null);
      setLine($("cur"), cue);
      setLine($("next"), idx + 1 < cues.length ? cues[idx + 1] : null);
      fillLine($("prev"), idx > 0 ? cues[idx - 1] : null, 1e12);
      fillLine($("cur"), cue, t);
      fillLine($("next"), idx + 1 < cues.length ? cues[idx + 1] : null, -1);
      hideNativeLyrics();
    } else if (upcoming >= 0) {
      held = upcoming > 0 ? cues[upcoming - 1] : cues[upcoming];
      setLine($("prev"), upcoming > 1 ? cues[upcoming - 2] : null);
      setLine($("cur"), held);
      setLine($("next"), held === cues[upcoming] ? (cues[upcoming + 1] || null) : cues[upcoming]);
      fillLine($("prev"), upcoming > 1 ? cues[upcoming - 2] : null, 1e12);
      fillLine($("cur"), held, held === cues[upcoming] ? -1 : 1e12);
      fillLine($("next"), held === cues[upcoming] ? (cues[upcoming + 1] || null) : cues[upcoming], -1);
      hideNativeLyrics();
    } else if (cues.length) {
      setLine($("prev"), cues[cues.length - 1]);
      setLine($("cur"), null);
      setLine($("next"), null);
      fillLine($("prev"), cues[cues.length - 1], 1e12);
      hideNativeLyrics();
    }
    syncNativeVideo(karaoke);
    var mtv = $("mtv");
    if (hasNativePlayer()) {
      if (mtv) {
        mtv.pause();
        if (mtv.getAttribute("src")) mtv.removeAttribute("src");
      }
      return;
    }
    if (mtv && karaoke && !karaoke.paused && mtv.src && mtv.paused) {
      mtv.muted = true;
      mtv.volume = 0;
      playEl(mtv);
    }
  }

  function tick() {
    if (moduleOwnsPlayback()) return;
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
      var key = (now.id || now.song_id) + ":" + (now.media_rev || "");
      if (lastItem !== key) {
        lastItem = key;
        stopSong();
        startSong(now);
      } else {
        applyMix();
        var karaoke = $("karaoke");
        if (karaoke && (karaoke.ended || (karaoke.duration > 2 && karaoke.currentTime >= karaoke.duration - 1.5))) {
          skip();
        } else if (karaoke && karaoke.paused && karaoke.getAttribute("src") && !karaoke.ended) {
          playEl(karaoke);
        }
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

  function moduleOwnsPlayback() {
    return !!(window.LovKtvRemote && (window.LovKtvRemote.__ready || window.LovKtvRemote.__module));
  }

  function startClassic(force) {
    if (moduleOwnsPlayback()) return;
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
    if (hasNativePlayer()) return;
    setTimeout(function () {
      if (moduleOwnsPlayback()) return;
      startClassic(true);
    }, 8000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
