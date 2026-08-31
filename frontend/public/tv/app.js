import "./install.js";
import { bootI18n, onLangChange, applyDom } from "../shared/i18n/js/i18n.js";
import { $, setDomRoot } from "../shared/ui/js/dom.js";
import { state } from "./state.js";
import { bootAuth, renderUserChip, stopAuthTimers } from "./auth/js/login.js";
import { unlockAudio } from "./audio/js/unlock.js";
import { bindRoomRtc } from "./audio/js/mic.js";
import { applyMix } from "./playback/js/media/mix.js";
import {
  tick,
  applyRoom,
  closeRoomWs,
  watchRoom,
  startPlayback,
  pauseAudio,
  restoreResume,
  songReallyEnded,
  wantsResume
} from "./playback/js/runtime/tick.js";
import { disposePaint, startPaint } from "./playback/js/lyric/paint.js";
import { bindRemote, skipSong, toggleVocal, paintSettings } from "./playback/js/remote/controls.js";
import { api, installApi } from "./api.js";
import { installPlatform } from "./platform.js";
import { stopKeepAlive } from "./audio/js/keepalive.js";

const mounted = new WeakSet();

/** @param {ParentNode} root @param {TvMountDeps} [deps] */
export function mount(root, deps = {}) {
  if (!root || mounted.has(root)) return () => {};
  mounted.add(root);
  let active = true;
  const cleanups = [];
  const listen = (target, event, handler, options) => {
    target.addEventListener(event, handler, options);
    cleanups.push(() => target.removeEventListener(event, handler, options));
  };
  if (deps.api) installApi(/** @type {TvApi} */ ({ ...api, ...deps.api }));
  if (deps.platform) installPlatform(deps.platform);
  const restoreDom = setDomRoot(root);
  /** @param {string} id */
  const must = (id) => {
    const el = $(id, root);
    if (!el) throw new Error("missing #" + id);
    return el;
  };

  bootI18n();
  cleanups.push(
    onLangChange(() => {
      applyDom();
      renderUserChip();
      applyMix();
      paintSettings();
    })
  );

  if (state.audioBus) {
    const onAudioMessage = (event) => {
      if (event.data && event.data.type === "claim" && event.data.tabId !== state.tabId && state.isLeader) {
        state.isLeader = false;
        pauseAudio();
      }
    };
    state.audioBus.onmessage = onAudioMessage;
    cleanups.push(() => {
      if (state.audioBus) state.audioBus.onmessage = null;
    });
  }
  const onVisibility = () => {
    if (state.room && state.room.paused) return;
    if (state.armed && state.room && state.room.now_playing) startPlayback();
  };
  listen(document, "visibilitychange", onVisibility);

  must("start").onclick = () => {
    unlockAudio();
    startPlayback();
  };
  const onPointer = () => {
    unlockAudio();
    if (state.room && state.room.paused) return;
    const karaoke = must("karaoke");
    if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
      startPlayback();
    }
  };
  listen(document, "pointerdown", onPointer);
  const onKeydown = () => {
    unlockAudio();
    if (state.room && state.room.paused) return;
    const karaoke = must("karaoke");
    if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
      startPlayback();
    }
  };
  listen(document, "keydown", onKeydown);
  must("skip").onclick = () => skipSong();
  must("toggle").onclick = () => toggleVocal();
  const onEnded = () => {
    const karaoke = must("karaoke");
    if (karaoke.ended && songReallyEnded(karaoke)) {
      skipSong();
      return;
    }
    restoreResume(karaoke);
    if (state.armed && state.room && state.room.now_playing) startPlayback();
  };
  listen(must("karaoke"), "ended", onEnded);
  const unbindRemote = bindRemote() || (() => {});
  cleanups.push(unbindRemote);

  const tickTimer = setInterval(tick, 1500);
  bootAuth()
    .then(() => {
      if (!active) return;
      bindRoomRtc(state.room.code);
      watchRoom(state.room.code, applyRoom);
      tick();
      startPaint();
    })
    .catch((err) => {
      const qr = $("qr", root);
      if (qr && qr.querySelector("canvas, img, svg")) return;
      const code = $("code", root);
      if (code) code.textContent = "开房失败";
      if (qr) qr.textContent = (err && err.message) || "请按菜单键检查处理服务器";
    });
  return () => {
    active = false;
    clearInterval(tickTimer);
    disposePaint();
    stopKeepAlive();
    closeRoomWs();
    stopAuthTimers();
    cleanups
      .splice(0)
      .reverse()
      .forEach((cleanup) => cleanup());
    ["start", "skip", "toggle"].forEach((id) => {
      const el = $(id, root);
      if (el) el.onclick = null;
    });
    restoreDom();
    mounted.delete(root);
  };
}

if (typeof document !== "undefined") mount(document.body || document);
