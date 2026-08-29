from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_phone_app_does_not_force_tv_on_boot():
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    join = (ROOT / "phone" / "room" / "js" / "join.js").read_text(encoding="utf-8")
    origin = (ROOT / "phone" / "origin.js").read_text(encoding="utf-8")
    pages = (ROOT / "phone" / "nav" / "js" / "pages.js").read_text(encoding="utf-8")
    html = (ROOT / "m.html").read_text(encoding="utf-8")
    assert "export function tvBound" in origin
    assert "export function requestTvBind" in join
    assert "export function hasNativeScan" in join
    assert "platformScanTv" in join
    assert "hasNativeScan() && !tvBound()" not in app
    assert "? \"player\" : \"desk\"" not in app
    assert 'bootPage = PAGES.includes(bootHash) ? bootHash : "desk"' in app
    assert '!$must("room").value) openOverlay("roomSheet")' not in app
    assert 'if (bootHash === "room") openOverlay("roomSheet")' in app
    assert 'btn.dataset.nav === "desk" && api.requestTvBind' not in pages
    assert "if (requestTvBind())" not in join
    assert "export function scanTv" in join
    assert "export function paintBindBtns" in join
    assert 'id="scanTv"' in html
    assert 'id="rebindTv"' in html
    assert "phone.room.scan" in html
    assert "phone.room.bind" in html
    assert "phone.top.unbound" in (ROOT / "phone" / "ui" / "js" / "icons.js").read_text(encoding="utf-8")


def test_queue_needs_room_not_forced_tv_scan():
    lib = (ROOT / "phone" / "desk" / "js" / "library.js").read_text(encoding="utf-8")
    mix = (ROOT / "phone" / "room" / "js" / "mix.js").read_text(encoding="utf-8")
    rtc = (ROOT / "phone" / "room" / "js" / "rtc.js").read_text(encoding="utf-8")
    playback = "\n".join((ROOT / "phone" / "player" / "js" / name).read_text(encoding="utf-8") for name in ("controls.js", "song.js"))
    join = (ROOT / "phone" / "room" / "js" / "join.js").read_text(encoding="utf-8")
    assert "api.needTvOrRoom" in lib
    assert "api.needTvOrRoom" in mix
    assert "api.needTvOrRoom" in rtc
    assert "requestTvBind()" not in join.split("export function needTvOrRoom")[1].split("export function")[0]
    assert "api.requestTvBind && api.requestTvBind()" not in playback
    assert "api.requestTvBind && api.requestTvBind()" in rtc
    assert "phone.mic.needTv" in rtc
    assert 'openOverlay("roomSheet")' in join


def test_scan_reload_uses_url_room_and_waits_for_lan():
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    join = (ROOT / "phone" / "room" / "js" / "join.js").read_text(encoding="utf-8")
    queue = (ROOT / "phone" / "desk" / "js" / "queue.js").read_text(encoding="utf-8")
    http = (ROOT / "shared" / "ui" / "js" / "http.js").read_text(encoding="utf-8")
    assert 'const roomFromUrl = (params.get("room") || "").toUpperCase();' in app
    assert 'localStorage.setItem("room", roomFromUrl)' in app
    assert "function waitLanReady()" in join
    assert "await waitLanReady();" in join
    assert "await api.loadRoom({ quiet: !!quiet });" in join
    assert "const quiet = !!(opts && opts.quiet);" in queue
    platform = (ROOT / "phone" / "platform.js").read_text(encoding="utf-8")
    assert "nativeHttpReady" in join
    assert "LovKtvPlatform" in http
    assert "phonePlatform" in platform
    origin = (ROOT / "phone" / "origin.js").read_text(encoding="utf-8")
    assert "export function adoptLan" in origin
    assert "platformUseLan" in origin
    assert "room.lan_origin" in origin
    assert "adoptLan" in join
    assert "if (adoptLan(room))" in join
    queue_js = (ROOT / "phone" / "desk" / "js" / "queue.js").read_text(encoding="utf-8")
    assert "adoptLan(cloud.data)" in queue_js
    assert "api.loadRoom({ room: data })" in (ROOT / "phone" / "desk" / "js" / "library.js").read_text(encoding="utf-8")
