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
    assert "function installApi" in (FRONTEND / "public" / "tv" / "api.js").read_text(encoding="utf-8")
    assert "installApi({" in (FRONTEND / "public" / "phone" / "install.js").read_text(encoding="utf-8")


def test_frontend_tsc_no_emit():
    tsc = FRONTEND / "node_modules" / ".bin" / "tsc"
    if tsc.exists():
        cmd = [str(tsc), "-p", str(FRONTEND), "--noEmit"]
    elif shutil.which("npx"):
        cmd = ["npx", "--yes", "typescript@5.9.2", "tsc", "-p", str(FRONTEND), "--noEmit"]
    else:
        pytest.skip("需要 Node，才能跑 frontend 的 tsc 检查")
    result = subprocess.run(cmd, cwd=FRONTEND, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
