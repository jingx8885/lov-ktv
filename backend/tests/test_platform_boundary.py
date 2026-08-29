"""Cross-target platform port smoke checks."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_adapter_has_same_named_ports():
    source = (ROOT / "tv" / "platform.js").read_text(encoding="utf-8")
    assert "export const tvPlatform" in source
    for port in ("http", "media", "mic", "remote", "scanner"):
        assert f"  {port}:" in source


def test_shared_http_does_not_know_android_bridge_name():
    source = (ROOT / "shared" / "ui" / "js" / "http.js").read_text(encoding="utf-8")
    assert "LovKtvPhone" not in source
    assert "LovKtvNative" not in source
    assert "LovKtvPlatform" in source
