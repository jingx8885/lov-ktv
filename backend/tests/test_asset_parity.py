import hashlib
import json
import runpy
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-asset-parity.py"


def _module():
    return runpy.run_path(str(SCRIPT), run_name="asset_parity")


def _bundle(tmp_path: Path):
    module = _module()
    files = {
        "index.html": b"index\n",
        "tv.html": b"tv\n",
        "m.html": b"phone\n",
        "tv/app.js": b"app\n",
    }
    root = tmp_path / "dist"
    root.mkdir()
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(files[relative])
        digest.update(b"\0")
    content_sha256 = digest.hexdigest()
    manifest = {
        "schema": 1,
        "revision": content_sha256[:12],
        "content_sha256": content_sha256,
        "files": {
            relative: hashlib.sha256(data).hexdigest()
            for relative, data in files.items()
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return module, root, files, manifest


def _archive(path: Path, files: dict[str, bytes], manifest: dict[str, object]):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("assets/web/manifest.json", json.dumps(manifest))
        for relative, data in files.items():
            archive.writestr("assets/web/" + relative, data)


def test_archive_parity_passes_and_reads_embedded_web_tree(tmp_path):
    module, root, files, manifest = _bundle(tmp_path)
    artifact = tmp_path / "tv.apk"
    _archive(artifact, files, manifest)
    failures = module["compare"](
        module["from_directory"](root), module["from_archive"](artifact)
    )
    assert failures == []


def test_parity_reports_hash_mismatch(tmp_path):
    module, root, files, manifest = _bundle(tmp_path)
    altered = dict(files, **{"tv.html": b"changed\n"})
    artifact = tmp_path / "tv.apk"
    _archive(artifact, altered, manifest)
    failures = module["compare"](
        module["from_directory"](root), module["from_archive"](artifact)
    )
    assert any("hash mismatch: tv.html" in failure for failure in failures)


def test_parity_reports_missing_file(tmp_path):
    module, root, files, manifest = _bundle(tmp_path)
    reference = module["from_directory"](root)
    artifact = module["Bundle"](
        manifest, {key: value for key, value in files.items() if key != "m.html"}
    )
    failures = module["compare"](reference, artifact)
    assert "missing paths: m.html" in failures


def test_parity_reports_revision_mismatch(tmp_path):
    module, root, files, manifest = _bundle(tmp_path)
    artifact_manifest = dict(manifest, revision="different")
    artifact = module["Bundle"](artifact_manifest, files)
    failures = module["compare"](module["from_directory"](root), artifact)
    assert any("manifest revision mismatch" in failure for failure in failures)


def test_missing_artifact_is_explicit_skip_or_enforced(tmp_path, capsys):
    module = _module()
    assert module["main"](["--reference", str(tmp_path)]) == 0
    assert "SKIP" in capsys.readouterr().out
    assert module["main"](["--reference", str(tmp_path), "--require-artifact"]) == 2
