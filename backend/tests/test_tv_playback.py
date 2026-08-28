from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_does_not_restart_on_network_stall():
    tick = (ROOT / "tv" / "playback" / "js" / "tick.js").read_text(encoding="utf-8")
    app = (ROOT / "tv" / "app.js").read_text(encoding="utf-8")
    keep = (ROOT / "tv" / "audio" / "js" / "keepalive.js").read_text(encoding="utf-8")
    mix = (ROOT / "tv" / "playback" / "js" / "mix.js").read_text(encoding="utf-8")
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "export function songReallyEnded" in tick
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
    assert 'src="/tv/app.js?v=split14"' in html
    assert "tick.js?v=stall1" in app
