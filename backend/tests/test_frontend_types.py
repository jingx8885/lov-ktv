import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def test_frontend_type_contracts_exist():
    assert (FRONTEND / "tsconfig.json").is_file()
    assert (FRONTEND / "package.json").is_file()
    for name in ("models.d.ts", "globals.d.ts", "phone-api.d.ts", "tv-api.d.ts"):
        assert (FRONTEND / "types" / name).is_file(), name
    phone_api = (FRONTEND / "public" / "phone" / "api.js").read_text(encoding="utf-8")
    tv_api = (FRONTEND / "public" / "tv" / "api.js").read_text(encoding="utf-8")
    assert "@type {PhoneApi}" in phone_api
    assert "function installApi" in phone_api
    assert "@type {TvApi}" in tv_api
    assert "function installApi" in (FRONTEND / "public" / "tv" / "api.js").read_text(
        encoding="utf-8"
    )
    assert "installApi({" in (FRONTEND / "public" / "phone" / "install.js").read_text(
        encoding="utf-8"
    )


def test_shared_visual_assets_are_inside_type_boundary():
    config = json.loads((FRONTEND / "tsconfig.json").read_text(encoding="utf-8"))
    includes = set(config["include"])
    excludes = set(config.get("exclude", []))
    assert "public/phone/player/js/timeline.js" in includes
    assert "public/tv/fx/js/stage-fx.js" in includes
    assert "public/phone/player/js/timeline.js" not in excludes
    assert "public/tv/fx/js/stage-fx.js" not in excludes

    # Phone modules must consume the shared bridge contracts, never TV modules.
    phone_root = FRONTEND / "public" / "phone"
    phone_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in phone_root.rglob("*.js")
    )
    assert "/tv/" not in phone_sources
    assert "/tv/" not in (FRONTEND / "public" / "m.html").read_text(encoding="utf-8")
    globals_text = (FRONTEND / "types" / "globals.d.ts").read_text(encoding="utf-8")
    for symbol in ("LovI18n", "LovKtvNative", "LovKtvOnHttp", "LovKtvOnMic"):
        assert symbol in globals_text


def test_frontend_tsc_no_emit():
    tsc = FRONTEND / "node_modules" / ".bin" / "tsc"
    if tsc.exists():
        # npm installs POSIX sh launchers alongside .cmd on Windows; invoke
        # the platform-native launcher so the contract test works everywhere.
        if os.name == "nt" and tsc.with_suffix(".cmd").exists():
            cmd = [str(tsc.with_suffix(".cmd")), "-p", str(FRONTEND), "--noEmit"]
        else:
            cmd = [str(tsc), "-p", str(FRONTEND), "--noEmit"]
    elif shutil.which("npx.cmd") or shutil.which("npx"):
        # ``npx`` resolves to a PowerShell shim on Windows, which cannot be
        # launched by subprocess without a shell.  Prefer the native .cmd
        # launcher so this contract test is portable across developer hosts.
        launcher = "npx.cmd" if os.name == "nt" and shutil.which("npx.cmd") else "npx"
        cmd = [
            launcher,
            "--yes",
            "--package",
            "typescript@5.9.2",
            "tsc",
            "-p",
            str(FRONTEND),
            "--noEmit",
        ]
    else:
        pytest.skip("需要 Node，才能跑 frontend 的 tsc 检查")
    result = subprocess.run(
        cmd, cwd=FRONTEND, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
