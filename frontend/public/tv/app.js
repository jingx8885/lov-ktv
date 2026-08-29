import "./install.js";
import { bootI18n, onLangChange, applyDom } from "../shared/i18n/js/i18n.js";
import { $, setDomRoot } from "../shared/ui/js/dom.js";
import { state } from "./state.js";
import { bootAuth, renderUserChip } from "./auth/js/login.js";
import { unlockAudio } from "./audio/js/unlock.js";
import { bindRoomRtc } from "./audio/js/mic.js";
import { applyMix } from "./playback/js/media/mix.js";
import {
  tick,
  applyRoom,
  watchRoom,
  startPlayback,
  pauseAudio,
  pageVisible,
  restoreResume,
  songReallyEnded,
  wantsResume
} from "./playback/js/runtime/tick.js";
import { paint } from "./playback/js/lyric/paint.js";
import { bindRemote, skipSong, toggleVocal, paintSettings } from "./playback/js/remote/controls.js";
import { api, installApi } from "./api.js";
import { installPlatform } from "./platform.js";

const mounted = new WeakSet();

/** @param {ParentNode} root @param {TvMountDeps} [deps] */
export function mount(root, deps = {}) {
  if (!root || mounted.has(root)) return () => {};
  mounted.add(root);
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
  onLangChange(() => {
    applyDom();
    renderUserChip();
    applyMix();
    paintSettings();
  });

  if (state.audioBus) {
    state.audioBus.onmessage = (event) => {
      if (event.data && event.data.type === "claim" && event.data.tabId !== state.tabId && state.isLeader) {
        state.isLeader = false;
        pauseAudio();
      }
    };
  }
  document.addEventListener("visibilitychange", () => {
    if (!pageVisible()) {
      pauseAudio();
      return;
    }
    if (state.room && state.room.paused) return;
    if (state.armed && state.room && state.room.now_playing) startPlayback();
  });

  must("start").onclick = () => {
    unlockAudio();
    startPlayback();
  };
  document.addEventListener("pointerdown", () => {
    unlockAudio();
    if (state.room && state.room.paused) return;
    const karaoke = must("karaoke");
    if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
      startPlayback();
    }
  });
  document.addEventListener("keydown", () => {
    unlockAudio();
    if (state.room && state.room.paused) return;
    const karaoke = must("karaoke");
    if (state.room && state.room.now_playing && state.room.now_playing.status === "ready" && wantsResume(karaoke)) {
      startPlayback();
    }
  });
  must("skip").onclick = () => skipSong();
  must("toggle").onclick = () => toggleVocal();
  must("karaoke").addEventListener("ended", () => {
    const karaoke = must("karaoke");
    if (songReallyEnded(karaoke)) {
      skipSong();
      return;
    }
    restoreResume(karaoke);
    if (state.armed && state.room && state.room.now_playing) startPlayback();
  });
  bindRemote();

  const tickTimer = setInterval(tick, 1500);
  bootAuth()
    .then(() => {
      bindRoomRtc(state.room.code);
      watchRoom(state.room.code, applyRoom);
      tick();
      requestAnimationFrame(paint);
    })
    .catch((err) => {
      const qr = $("qr", root);
      if (qr && qr.querySelector("canvas, img, svg")) return;
      const code = $("code", root);
      if (code) code.textContent = "开房失败";
      if (qr) qr.textContent = (err && err.message) || "请按菜单键检查处理服务器";
    });
  return () => {
    clearInterval(tickTimer);
    restoreDom();
    mounted.delete(root);
  };
}

if (typeof document !== "undefined") mount(document.body || document);
