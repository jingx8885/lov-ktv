"""Static contract checks for the Phone platform adapter boundary."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"
PHONE = ROOT / "phone"


def test_phone_platform_exposes_named_ports_and_bridge_isolated():
    source = (PHONE / "platform.js").read_text(encoding="utf-8")
    assert "export const phonePlatform" in source
    for port in ("mic", "scanner", "media", "remote", "http"):
        assert f"  {port}:" in source
    assert "export const platform = phonePlatform" in source
    # Only the adapter may inspect the Android injection point.
    business = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PHONE.rglob("*.js")
        if path.name != "platform.js"
    )
    assert not re.search(r"window\.LovKtvPhone|window\.LovKtvNative", business)
    assert "window.LovKtvPlatform" in (ROOT / "shared" / "ui" / "js" / "http.js").read_text(encoding="utf-8")


def test_phone_platform_degrades_without_native_bridge():
    source = (PHONE / "platform.js").read_text(encoding="utf-8")
    assert "nativeCapabilities()" in source
    assert "nativeMicState()" in source
    assert 'return { native: false' in source
    assert "return false;" in source  # scanner and bridge calls are no-op safe
