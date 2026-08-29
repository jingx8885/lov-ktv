import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLAYER = ROOT / "frontend" / "public" / "phone" / "player" / "js"


def test_phone_playback_has_responsibility_modules_and_facade_exports():
    for name in ("media.js", "controls.js", "queue.js", "lyrics.js", "song.js", "ui.js"):
        assert (PLAYER / name).is_file(), name
    facade = (PLAYER / "playback.js").read_text(encoding="utf-8")
    for symbol in ("mediaUrl", "togglePlayer", "playNextSong", "paintPlayer", "loadPlayerSong", "bindPlayback"):
        assert symbol in facade, symbol
    assert len(facade.splitlines()) < 100


def test_phone_playback_modules_parse_and_facade_imports():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node，才能跑 phone playback smoke")
    for path in PLAYER.glob("*.js"):
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
    script = (
        "globalThis.localStorage={getItem:()=>null,setItem:()=>{}};"
        "const m=await import('./frontend/public/phone/player/js/playback.js');"
        "for (const n of ['mediaUrl','togglePlayer','playNextSong','paintPlayer','loadPlayerSong','bindPlayback']) "
        "if (typeof m[n] !== 'function') throw Error(n);"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
