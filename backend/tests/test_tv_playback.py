from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_does_not_restart_on_network_stall():
    tick = (ROOT / "tv" / "playback" / "js" / "tick.js").read_text(encoding="utf-8")
    playback_state = (ROOT / "tv" / "playback" / "js" / "state.js").read_text(encoding="utf-8")
    app = (ROOT / "tv" / "app.js").read_text(encoding="utf-8")
    keep = (ROOT / "tv" / "audio" / "js" / "keepalive.js").read_text(encoding="utf-8")
    mix = (ROOT / "tv" / "playback" / "js" / "mix.js").read_text(encoding="utf-8")
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "export function watchRoom" in tick
    assert "/ws/box/" in tick
    assert "export async function applyRoom" in tick
    assert "export function songReallyEnded" in tick
    assert 'from "./state.js"' in tick
    assert "export function mediaEndedAt" in playback_state
    assert "export function roomItemIdentity" in playback_state
    assert "export function shouldReloadRoomItem" in playback_state
    assert "export function wantsResume" in tick
    assert "export function restoreResume" in tick
    assert "if (t > 0.5)" in tick
    assert "state.emptyNow < 3" in tick
    assert 'karaoke.src = mediaUrl(songId, "original.mp3")' in tick
    assert "if (srcHasSong(karaoke, songId))" in tick
    assert "wantsResume(karaoke)" in tick
    assert "wantsResume(karaoke)" in keep
    assert 'addEventListener("ended", () => $must("skip").click())' not in app
    assert "if (songReallyEnded(karaoke))" in app
    assert "restoreResume(karaoke)" in app
    assert "item.song_id !== nowId" in mix
    assert 'if (now && now.status === "ready") add(now.song_id)' not in mix
    assert 'src="/tv/app.js"' in html
    assert 'from "./playback/js/tick.js"' in app
    assert "watchRoom(state.room.code, applyRoom)" in app
    assert "export function setWaiting" in tick
    assert "setWaiting(true)" in tick
    assert 'setWaiting(now.status !== "ready")' in tick
    remote = (ROOT / "tv" / "playback" / "js" / "remote.js").read_text(encoding="utf-8")
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
    silent = (ROOT.parent.parent / "android-tv" / "app" / "src" / "main" / "java" / "com" / "lovktv" / "tv" / "SilentMtv.kt").read_text(encoding="utf-8")
    activity = (ROOT.parent.parent / "android-tv" / "app" / "src" / "main" / "java" / "com" / "lovktv" / "tv" / "TvActivity.kt").read_text(encoding="utf-8")
    assert "setVideoScalingMode" not in silent
    assert "PixelFormat.OPAQUE" not in silent
    assert "resumeMtv()" in activity
    mtv = (ROOT / "tv" / "playback" / "js" / "mtv.js").read_text(encoding="utf-8")
    clock = (ROOT / "tv" / "playback" / "js" / "lyric-clock.js").read_text(encoding="utf-8")
    lyrics = (ROOT / "tv" / "playback" / "js" / "lyrics.js").read_text(encoding="utf-8")
    assert "LovKtvNative.playMtv" in mtv
    assert "export function shouldSeekNative" in clock
    assert "syncNativeVideo" in lyrics
    assert "window.LovKtvNative.stopMtv" in tick
