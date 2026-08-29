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
