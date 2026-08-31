import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLAYER = ROOT / "frontend" / "public" / "phone" / "player" / "js" / "playback"


def test_phone_playback_has_responsibility_modules_without_facade():
    for name in (
        "media.js",
        "controls.js",
        "queue.js",
        "lyrics.js",
        "song.js",
        "ui.js",
    ):
        assert (PLAYER / name).is_file(), name
    assert not (PLAYER / "playback.js").exists()


def test_phone_playback_modules_parse_and_direct_imports():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node，才能跑 phone playback smoke")
    for path in PLAYER.glob("*.js"):
        result = subprocess.run(
            [node, "--check", str(path)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr
    script = (
        "globalThis.localStorage={getItem:()=>null,setItem:()=>{}};"
        "const mods=await Promise.all(['media','controls','queue','lyrics','song','ui'].map(n=>import('./frontend/public/phone/player/js/playback/'+n+'.js')));"
        "for (const m of mods) if (!m || !Object.keys(m).length) throw Error('empty module');"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_phone_playback_keeps_lyrics_and_vocal_sync_on_a_bounded_cadence():
    controls = (PLAYER / "controls.js").read_text(encoding="utf-8")
    lyrics = (PLAYER / "lyrics.js").read_text(encoding="utf-8")
    ui = (PLAYER / "ui.js").read_text(encoding="utf-8")
    # Keep phone playback aligned with the TV runtime: rendering may continue
    # on RAF, but layout-heavy lyric work and corrective seeks are bounded.
    assert "lastGuideSyncAt" in controls
    assert "now - lastGuideSyncAt >= 400" in controls
    assert "const slack = forceTime != null ? 0.05 : 0.35" in controls
    assert "const targetReady = forceTime != null || mediaAhead(guide, clock) > 0.2" in controls
    assert "const frameNow = performance.now()" in lyrics
    assert "frameNow - lastPaintAt < 33" in lyrics
    # Event handlers only refresh UI/painting; guide correction has one owner.
    assert '() => syncGuide()' not in ui
