from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_phone_app_does_not_force_scan_on_boot():
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    join = (ROOT / "phone" / "room" / "js" / "join.js").read_text(encoding="utf-8")
    origin = (ROOT / "phone" / "origin.js").read_text(encoding="utf-8")
    pages = (ROOT / "phone" / "nav" / "js" / "pages.js").read_text(encoding="utf-8")
    html = (ROOT / "m.html").read_text(encoding="utf-8")
    assert "export function tvBound" in origin
    assert "export function requestTvBind" in join
    assert "export function hasNativeScan" in join
    assert "LovKtvPhone.scanTv" in join
    assert "hasNativeScan() && !tvBound()" in app
    assert 'bootPage = "player"' in app or "? \"player\" : \"desk\"" in app
    assert '!$must("room").value) openOverlay("roomSheet")' not in app
    assert 'if (bootHash === "room") openOverlay("roomSheet")' in app
    assert 'btn.dataset.nav === "desk" && api.requestTvBind' in pages
    assert "export function scanTv" in join
    assert "export function paintBindBtns" in join
    assert 'id="scanTv"' in html
    assert 'id="rebindTv"' in html
    assert "phone.room.scan" in html
    assert "phone.room.bind" in html
    assert "phone.top.unbound" in (ROOT / "phone" / "ui" / "js" / "icons.js").read_text(encoding="utf-8")


def test_queue_and_skip_ask_tv_bind_before_public_room():
    lib = (ROOT / "phone" / "desk" / "js" / "library.js").read_text(encoding="utf-8")
    mix = (ROOT / "phone" / "room" / "js" / "mix.js").read_text(encoding="utf-8")
    rtc = (ROOT / "phone" / "room" / "js" / "rtc.js").read_text(encoding="utf-8")
    playback = (ROOT / "phone" / "player" / "js" / "playback.js").read_text(encoding="utf-8")
    assert "api.needTvOrRoom" in lib
    assert "api.needTvOrRoom" in mix
    assert "api.needTvOrRoom" in rtc
    assert "api.requestTvBind && api.requestTvBind()" in playback
    assert 'openOverlay("roomSheet")' not in lib
