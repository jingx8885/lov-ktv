"""Lightweight smoke checks for the phone/TV HTML mount contract.

These tests intentionally parse the static entry points with the stdlib only;
no browser or bundler is required.  They catch accidental removal/renaming of
the mount roots that feature modules use during the R5A refactor.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"
ANDROID_PHONE = Path(__file__).resolve().parents[2] / "android-phone"


class _Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.attrs: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.attrs.append({"tag": tag, **{k: v or "" for k, v in attrs}})


def _parse(name: str) -> list[dict[str, str]]:
    parser = _Elements()
    parser.feed((ROOT / name).read_text(encoding="utf-8"))
    return parser.attrs


def _ids(elements: list[dict[str, str]]) -> set[str]:
    return {item["id"] for item in elements if item.get("id")}


def _must_ids(folder: str) -> set[str]:
    """Collect literal $must('id') references used during module startup."""
    found: set[str] = set()
    for path in (ROOT / folder).rglob("*.js"):
        found.update(
            re.findall(
                r"\$must\(\s*[\"']([^\"']+)[\"']\s*\)", path.read_text(encoding="utf-8")
            )
        )
    return found


def test_phone_entry_has_stable_mount_points_and_boot_module():
    elements = _parse("m.html")
    mounts = {item["data-mount"] for item in elements if "data-mount" in item}
    assert {
        "phone-root",
        "phone-app",
        "phone-topbar",
        "phone-search",
        "phone-desk",
        "phone-player",
        "phone-tabbar",
        "phone-room",
        "phone-room-sheet",
        "phone-who",
        "phone-who-sheet",
        "phone-language",
        "phone-mix",
        "phone-mix-sheet",
    } <= mounts
    body = next(item for item in elements if item.get("tag") == "body")
    assert body.get("data-app") == "phone"
    assert any(
        item.get("tag") == "script"
        and item.get("type") == "module"
        and item.get("src", "").endswith("/phone/app.js")
        for item in elements
    )
    assert _must_ids("phone") <= _ids(elements)
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    assert "export function mount(root, deps" in app
    assert "setDomRoot(root)" in app
    assert '$must("' not in app


def test_tv_entry_has_stable_mount_points_and_boot_module():
    elements = _parse("tv.html")
    mounts = {item["data-mount"] for item in elements if "data-mount" in item}
    assert {
        "tv-root",
        "tv-qr",
        "tv-settings",
        "tv-login",
        "tv-start",
        "tv-ui",
        "tv-lyrics",
        "tv-footer",
    } <= mounts
    body = next(item for item in elements if item.get("tag") == "body")
    assert body.get("data-app") == "tv"
    assert any(
        item.get("tag") == "script"
        and item.get("type") == "module"
        and item.get("src", "").endswith("/tv/app.js")
        for item in elements
    )
    assert _must_ids("tv") <= _ids(elements)
    app = (ROOT / "tv" / "app.js").read_text(encoding="utf-8")
    assert "export function mount(root, deps" in app
    assert "setDomRoot(root)" in app
    assert '$must("' not in app


def test_phone_tv_state_has_explicit_ownership_slices():
    for path, symbols in {
        ROOT / "phone" / "catalog" / "state.js": ("catalogState",),
        ROOT / "phone" / "room" / "state.js": ("roomState",),
        ROOT / "phone" / "player" / "state.js": ("playerState",),
        ROOT / "tv" / "room" / "state.js": ("roomState",),
        ROOT / "tv" / "playback" / "state.js": ("playbackState",),
        ROOT / "tv" / "audio" / "state.js": ("audioState",),
    }.items():
        source = path.read_text(encoding="utf-8")
        for symbol in symbols:
            assert f"export const {symbol}" in source


def test_android_phone_rebind_injection_uses_mount_contract():
    source = (
        ANDROID_PHONE
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "lovktv"
        / "phone"
        / "feature"
        / "DeskActivity.kt"
    ).read_text(encoding="utf-8")
    assert '[data-mount="phone-room-sheet"]' in source
    assert '[data-mount="phone-who-sheet"]' in source
    assert '[data-mount="phone-language"]' in source
    assert "#roomSheet .sheet" not in source
    assert ".lang-picker" not in source
