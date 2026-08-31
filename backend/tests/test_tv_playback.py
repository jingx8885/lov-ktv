from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_does_not_restart_on_network_stall():
    tick = (ROOT / "tv" / "playback" / "js" / "runtime" / "tick.js").read_text(
        encoding="utf-8"
    )
    playback_state = (
        ROOT / "tv" / "playback" / "js" / "runtime" / "state.js"
    ).read_text(encoding="utf-8")
    room_state = (ROOT / "tv" / "playback" / "js" / "room" / "state.js").read_text(
        encoding="utf-8"
    )
    platform = (ROOT / "tv" / "platform.js").read_text(encoding="utf-8")
    app = (ROOT / "tv" / "app.js").read_text(encoding="utf-8")
    keep = (ROOT / "tv" / "audio" / "js" / "keepalive.js").read_text(encoding="utf-8")
    mix = (ROOT / "tv" / "playback" / "js" / "media" / "mix.js").read_text(
        encoding="utf-8"
    )
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "export { closeRoomWs, roomWsLive, watchRoom }" in tick
    assert "/ws/rooms/" in room_state
    assert "/ws/box/" not in room_state
    assert "snapshotStamp" in room_state
    assert "export async function applyRoom" in tick
    assert "export function songReallyEnded" in tick
    assert 'from "./state.js"' in tick
    assert "export function mediaEndedAt" in playback_state
    assert "export function roomItemIdentity" in playback_state
    assert "export function shouldReloadRoomItem" in playback_state
    assert "export function watchRoom" in room_state
    assert "export function fetchRoomSnapshot" in room_state
    assert 'from "../room/state.js"' in tick
    assert "export function wantsResume" in tick
    assert "export function restoreResume" in tick
    assert "if (t > 0.5)" in tick
    assert "export function shouldStopEmptyNow" in playback_state
    assert "if (shouldStopEmptyNow(now))" in tick
    assert "state.emptyNow < 3" not in tick
    assert "if (roomWsLive() && state.room && state.room.code)" not in tick
    assert "fetchRoomSnapshot(code)" in tick
    assert "stopAudioOnly();" in tick
    handler = (
        ROOT.parent.parent
        / "android-tv"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "lovktv"
        / "tv"
        / "feature"
        / "host"
        / "HostApiHandler.kt"
    ).read_text(encoding="utf-8")
    assert "kind is ApiKind.RoomSkip" in handler
    assert "RoomQueue || kind is ApiKind.RoomPlay || kind is ApiKind.RoomSkip" in handler
    assert "ensureActiveTrack(songId)" in tick
    assert "activeTrackName()" in tick
    assert 'const vocal = $("vocal")' not in tick
    assert "api.playEl(vocal)" not in tick
    assert "if (srcHasSong(karaoke, songId))" in tick
    assert "wantsResume(karaoke)" in tick
    assert "wantsResume(karaoke)" in keep
    assert 'addEventListener("ended", () => $must("skip").click())' not in app
    assert "karaoke.ended && songReallyEnded(karaoke)" in app
    assert "restoreResume(karaoke)" in app
    assert "item.song_id !== nowId" in mix
    assert 'if (now && now.status === "ready") add(now.song_id)' not in mix
    assert 'src="/tv/app.js"' in html
    # Playback is owned by the ES module app; the legacy classic bootstrap
    # installed a second polling/lyrics timer when module loading was delayed.
    assert 'src="/tv/boot-play.js"' not in html
    assert 'from "./playback/js/runtime/tick.js"' in app
    assert "watchRoom(state.room.code, applyRoom)" in app
    assert "startPaint();" in app
    assert "disposePaint();" in app
    assert "stopAuthTimers();" in app
    assert "clearInterval(tickTimer);" in app
    assert "export function setWaiting" in tick
    assert "setWaiting(true)" in tick
    assert 'setWaiting(now.status !== "ready")' in tick
    remote = (ROOT / "tv" / "playback" / "js" / "remote" / "controls.js").read_text(
        encoding="utf-8"
    )
    assert "togglePaused" in remote
    assert "if (startIfNeeded()) return;" in remote
    assert "if (startIfNeeded() && roomPaused()) return;" not in remote
    assert "moveSettings" in remote
    assert "settingsItems" in remote
    assert "if (settingsOpen()) moveSettings(-1)" in remote
    assert "if (settingsOpen()) moveSettings(1)" in remote
    assert 'id="tvSheet"' in html
    assert 'id="tvSkip"' in html
    assert 'id="tvVocalValue"' in html
    assert "tv-menu-item" in html
    assert "data-tv-menu" in html
    assert "确认 暂停/播放" in html
    arrow_up = remote.split('case "ArrowUp":', 1)[1].split("case ", 1)[0]
    assert "moveSettings(-1)" in arrow_up
    assert "nudgeVolume(5)" in arrow_up
    arrow_down = remote.split('case "ArrowDown":', 1)[1].split("case ", 1)[0]
    assert "moveSettings(1)" in arrow_down
    assert "nudgeVolume(-5)" in arrow_down
    silent = (
        ROOT.parent.parent
        / "android-tv"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "lovktv"
        / "tv"
        / "media"
        / "SilentMtv.kt"
    ).read_text(encoding="utf-8")
    activity = (
        ROOT.parent.parent
        / "android-tv"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "lovktv"
        / "tv"
        / "ui"
        / "TvActivity.kt"
    ).read_text(encoding="utf-8")
    assert "setVideoScalingMode" not in silent
    assert "PixelFormat.OPAQUE" not in silent
    assert "resumeMtv()" in activity
    assert "pauseNativeMtv()" in tick
    keys = (
        ROOT.parent.parent
        / "android-tv"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "lovktv"
        / "tv"
        / "ui"
        / "RemoteKeys.kt"
    ).read_text(encoding="utf-8")
    assert "KEYCODE_DPAD_CENTER" in keys
    assert "KeyEvent.KEYCODE_DPAD_CENTER," in keys.split("fun interceptInNative")[1]
    mtv = (ROOT / "tv" / "playback" / "js" / "media" / "mtv.js").read_text(
        encoding="utf-8"
    )
    clock = (ROOT / "tv" / "playback" / "js" / "lyric" / "clock.js").read_text(
        encoding="utf-8"
    )
    lyrics = (ROOT / "tv" / "playback" / "js" / "lyric" / "paint.js").read_text(
        encoding="utf-8"
    )
    assert "nativeMtvAvailable" in mtv
    assert "export function playNativeMtv" in platform
    assert "export function shouldSeekNative" in clock
    assert "syncNativeVideo" in lyrics
    assert "stopNativeMtv" in tick


def test_tv_has_one_runtime_owner_and_no_legacy_boot_entries():
    """The ES-module runtime is the only TV bootstrap for browser and APK WebView."""
    tv = (ROOT / "tv.html").read_text(encoding="utf-8")
    app = (ROOT / "tv" / "app.js").read_text(encoding="utf-8")
    remote = (ROOT / "tv" / "playback" / "js" / "remote" / "controls.js").read_text(
        encoding="utf-8"
    )
    scripts = [p.read_text(encoding="utf-8") for p in (ROOT / "tv").rglob("*.js")]
    joined = "\n".join(scripts)

    assert 'src="/tv/app.js"' in tv
    assert 'src="/tv/boot-play.js"' not in tv
    assert 'src="/tv/boot-qr.js"' not in tv
    assert not (ROOT / "tv" / "boot-play.js").exists()
    assert not (ROOT / "tv" / "boot-qr.js").exists()
    assert joined.count("window.LovKtvRemote =") == 1
    assert joined.count("setInterval(tick, 1500)") == 1
    assert app.count("setInterval(tick, 1500)") == 1
    assert "bindRemote()" in app
    assert "__module: true" in remote


def test_browser_room_websocket_contract_is_shared_and_safe():
    """TV snapshots and phone RTC must use the canonical encoded room socket."""
    room_state = (ROOT / "tv" / "playback" / "js" / "room" / "state.js").read_text(
        encoding="utf-8"
    )
    mic = (ROOT / "shared" / "audio" / "js" / "rtc" / "mic.js").read_text(
        encoding="utf-8"
    )
    scripts = [p.read_text(encoding="utf-8") for p in ROOT.rglob("*.js")]
    joined = "\n".join(scripts)

    # There must be one public room WebSocket route; an obsolete route would be
    # caught by static-file handling instead of the room WebSocket endpoint.
    assert "/ws/" + "box" not in joined
    for source in (room_state, mic):
        assert '"/ws/rooms/"' in source
        assert "encodeURIComponent" in source
        assert 'location.protocol === "https:" ? "wss:" : "ws:"' in source


def test_tv_cold_start_pause_skip_stall_and_mtv_degrade_contracts():
    """Keep the critical playback transitions covered without a browser dependency."""
    app = (ROOT / "tv" / "app.js").read_text(encoding="utf-8")
    tick = (ROOT / "tv" / "playback" / "js" / "runtime" / "tick.js").read_text(
        encoding="utf-8"
    )
    remote = (ROOT / "tv" / "playback" / "js" / "remote" / "controls.js").read_text(
        encoding="utf-8"
    )
    mtv = (ROOT / "tv" / "playback" / "js" / "media" / "mtv.js").read_text(
        encoding="utf-8"
    )
    mix = (ROOT / "tv" / "playback" / "js" / "media" / "mix.js").read_text(
        encoding="utf-8"
    )
    html = (ROOT / "tv.html").read_text(encoding="utf-8")

    # Cold start is explicitly armed by the same button in browser and APK WebView.
    assert 'must("start").onclick' in app
    assert "unlockAudio();" in app
    assert "startPlayback();" in app
    assert "watchRoom(state.room.code, applyRoom)" in app
    # Pause/resume is room-authoritative and never advances while paused.
    assert "if (state.room && state.room.paused)" in tick
    assert "pauseAudio();" in tick
    assert "export function applyPaused()" in remote
    assert "startPlayback();" in remote
    # Skip clears the current item and re-enters the canonical tick path.
    assert 'fetchJson("/api/rooms/" + code + "/skip"' in remote
    assert 'state.lastItem = ""' in remote
    assert "await tick();" in remote
    # Stalls retain resume position and are excluded from eager restart decisions.
    assert 'addEventListener("waiting"' in tick
    assert 'addEventListener("stalled"' in tick
    assert "state.mediaStall" in tick
    assert "if (isMediaStalled(el)) return false;" in tick
    assert "state.resumeAt = t;" in tick
    # canplay may fire before playback actually resumes; only playing should
    # clear the stall guard so the vocal cannot restart during that gap.
    assert 'el.addEventListener("canplay"' not in tick
    # TV playback has one audio element; changing original/backing replaces
    # its source instead of running a second track and synchronising it.
    assert "export function ensureActiveTrack" in mix
    assert 'audio.src = url' in mix
    assert 'id="vocal"' not in html
    assert "if (stamp === state.lastRoomStamp) return;" in tick
    assert "karaoke.readyState >= 3" in tick
    assert "!state.mediaStall" in tick
    # Browser MTV failure degrades to a cover; native MTV remains the same bind path.
    assert "mtv.onerror = () =>" in mtv
    assert 'classList.add("has-mtv-cover")' in mtv
    assert "mtv.hidden = true" in mtv
    assert "playNativeMtv" in mtv


def test_tv_runtime_lifecycle_and_rendering_are_bounded():
    app = (ROOT / "tv" / "app.js").read_text(encoding="utf-8")
    paint = (ROOT / "tv" / "playback" / "js" / "lyric" / "paint.js").read_text(
        encoding="utf-8"
    )
    room = (ROOT / "tv" / "playback" / "js" / "room" / "state.js").read_text(
        encoding="utf-8"
    )
    # A repeated mount of the same root is a no-op; a real unmount removes all
    # timers, listeners, websocket and animation-frame resources.
    assert "const mounted = new WeakSet()" in app
    assert "if (!root || mounted.has(root)) return () => {};" in app
    assert "cleanups" in app and "reverse()" in app
    assert "removeEventListener" in app
    assert "clearInterval(tickTimer)" in app
    assert "cancelAnimationFrame(paintFrame)" in paint
    assert 'global.removeEventListener("resize", resize)' in (
        ROOT / "shared" / "fx" / "js" / "stage" / "runtime.js"
    ).read_text(encoding="utf-8")
    # Duplicate snapshots are discarded and lyric DOM work is capped at ~30fps
    # while the canvas animation may continue at requestAnimationFrame cadence.
    assert "if (stamp === roomWsStamp) return;" in room
    assert "const drawLyrics = frameNow - lastLyricPaintAt >= 33;" in paint
    assert "if (paintActive) paintFrame = requestAnimationFrame(paint);" in paint
    mtv = (ROOT / "tv" / "playback" / "js" / "media" / "mtv.js").read_text(
        encoding="utf-8"
    )
    loaded = mtv.split("mtv.onloadeddata = () =>", 1)[1].split("mtv.src =", 1)[0]
    assert ".play()" not in loaded
