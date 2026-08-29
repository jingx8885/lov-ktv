import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "frontend" / "public" / "shared" / "fx" / "js"


def test_stage_fx_is_split_into_ordered_modules():
    tv = (ROOT / "frontend" / "public" / "tv.html").read_text(encoding="utf-8")
    scripts = [
        "/shared/fx/js/stage/primitives.js",
        "/shared/fx/js/stage/build.js",
        "/shared/fx/js/stage/draw.js",
        "/shared/fx/js/stage/runtime.js",
        "/shared/fx/js/stage/party.js",
        "/shared/fx/js/stage/hooks.js",
    ]
    positions = [tv.index(f'src="{src}"') for src in scripts]
    assert positions == sorted(positions)
    assert all(
        (ROOT / "frontend" / "public" / src.lstrip("/")).is_file() for src in scripts
    )
    assert not (FX / "stage-fx.js").exists()


def test_stage_fx_browser_smoke():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node，才能运行 stage-fx smoke")
    files = [
        FX / "stage" / "primitives.js",
        FX / "stage" / "build.js",
        FX / "stage" / "draw.js",
        FX / "stage" / "runtime.js",
        FX / "stage" / "party.js",
        FX / "stage" / "hooks.js",
    ]
    script = r"""
const fs = require("fs");
const vm = require("vm");
const files = JSON.parse(process.argv[1]);
const context = {
  console,
  Math,
  performance: { now: () => 1000 },
  devicePixelRatio: 1,
  matchMedia: () => ({ matches: false }),
  addEventListener: () => {},
};
context.window = context;
const methods = ["setTransform", "clearRect", "save", "restore", "translate", "scale", "rotate",
  "beginPath", "closePath", "moveTo", "lineTo", "arc", "fill", "stroke", "fillRect", "clip"];
const ctx = {};
for (const method of methods) ctx[method] = () => {};
Object.assign(ctx, { globalAlpha: 1, fillStyle: "", strokeStyle: "", lineWidth: 1, lineJoin: "", lineCap: "" });
const canvas = {
  width: 0, height: 0, clientWidth: 640, clientHeight: 360,
  getBoundingClientRect: () => ({ width: 640, height: 360 }),
  getContext: () => ctx,
};
for (const file of files) vm.runInNewContext(fs.readFileSync(file, "utf8"), context, { filename: file });
if (!context.LovStageFxRuntime || context.LovStageFxPrimitives.EFFECTS.length !== 12) throw new Error("runtime missing");
const fx = context.LovStageFxRuntime.create(canvas);
for (const effect of context.LovStageFxPrimitives.EFFECTS) {
  if (fx.spawn(effect) !== effect) throw new Error("spawn failed: " + effect);
  fx.draw({ now: 1.2, beat: 0.4 });
}
fx.clear();
if (context.LovStageFxTextHooks.hookTexts([{text:"x"},{text:"x"},{text:"x"}]).size !== 1) throw new Error("hookTexts failed");
"""
    result = subprocess.run(
        [node, "-e", script, json.dumps([str(path) for path in files])],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
