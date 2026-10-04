import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "frontend" / "public"
PHONE = PUBLIC / "phone"
TESTS = ROOT / "frontend" / "tests"


def test_media_cache_files_exist_and_parse():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node，才能跑 media cache smoke")
    for path in (PUBLIC / "sw-media.js", PHONE / "media-cache.js"):
        result = subprocess.run(
            [node, "--check", str(path)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_media_cache_service_worker_behaviour():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node，才能跑 service worker 行为测试")
    result = subprocess.run(
        [node, "--test", str(TESTS / "media-cache-sw.test.mjs")],
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_phone_app_registers_media_cache_worker():
    app = (PHONE / "app.js").read_text(encoding="utf-8")
    helper = (PHONE / "media-cache.js").read_text(encoding="utf-8")
    song = (
        PHONE / "player" / "js" / "playback" / "song.js"
    ).read_text(encoding="utf-8")
    assert 'from "./media-cache.js"' in app
    assert "bootMediaCache()" in app
    assert 'sw.register("/sw-media.js"' in helper
    assert "prefetchMedia(" in song
