import importlib.util
import json
import zipfile
from pathlib import Path


def _module(name: str, filename: str):
    path = Path(__file__).resolve().parents[2] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_embedded_tv_apk_matches_frontend_manifest(tmp_path):
    build = _module("frontend_build", "build-frontend-dist.py")
    parity = _module("frontend_parity", "check-frontend-parity.py")
    source = tmp_path / "public"
    output = tmp_path / "frontend-dist"
    for name, body in {
        "tv.html": b'<script src="/tv/app.js"></script>',
        "m.html": b'<script src="/phone/app.js"></script>',
        "tv/app.js": b"export const tv = true;",
        "phone/app.js": b"export const phone = true;",
        "shared/ui.css": b"body{}",
    }.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    manifest = build.build(source, output)
    apk = tmp_path / "tv.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.write(output / "manifest.json", "assets/web/manifest.json")
        for path in manifest["files"]:
            archive.write(output / path, "assets/web/" + path)
    assert parity.check_apk(apk, manifest) == []

    broken = tmp_path / "broken.apk"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("assets/web/manifest.json", json.dumps(manifest))
        for path in manifest["files"]:
            data = (output / path).read_bytes()
            archive.writestr("assets/web/" + path, data + (b"!" if path.endswith("app.js") else b""))
    assert any("hash mismatch" in item for item in parity.check_apk(broken, manifest))
