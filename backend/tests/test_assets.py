import re
import json
import runpy
from pathlib import Path

from fastapi.testclient import TestClient

from lovktv.assets import _compute, asset_rev, reset_asset_rev_cache, rewrite_frontend_assets

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"
BUILD = Path(__file__).resolve().parents[2] / "scripts" / "build-frontend-dist.py"
ASSET_REF = re.compile(r"""['"]([^'"]+\.(?:js|css))\?v=([^'"]+)['"]""")


def test_rewrite_versions_frontend_refs_and_keeps_media():
    src = """
    import { x } from "./mix.js";
    import { y } from "./tick.js?v=native1";
    <script type="module" src="/tv/app.js"></script>
    <link rel="stylesheet" href="/tv/stage/css/stage.css?v=split10" />
    addModule("/shared/audio/js/aec/worklet.js");
    @import url("/shared/ui/css/tokens.css");
    const lyrics = `/media/${id}/lyrics.json?v=ja-kanji`;
    const stem = `/media/${id}/karaoke.m4a?v=stem2`;
    """
    out = rewrite_frontend_assets(src, "abc123")
    assert 'from "./mix.js?v=abc123"' in out
    assert 'from "./tick.js?v=abc123"' in out
    assert 'src="/tv/app.js?v=abc123"' in out
    assert 'href="/tv/stage/css/stage.css?v=abc123"' in out
    assert 'addModule("/shared/audio/js/aec/worklet.js?v=abc123")' in out
    assert '@import url("/shared/ui/css/tokens.css?v=abc123")' in out
    assert "`/media/${id}/lyrics.json?v=ja-kanji`" in out
    assert "`/media/${id}/karaoke.m4a?v=stem2`" in out


def test_source_js_html_have_no_manual_asset_versions():
    leftovers = []
    for path in sorted(list(ROOT.rglob("*.js")) + list(ROOT.rglob("*.html"))):
        text = path.read_text(encoding="utf-8")
        for match in ASSET_REF.finditer(text):
            url, ver = match.group(1), match.group(2)
            if "/media/" in url or "${" in url:
                continue
            leftovers.append(f"{path.relative_to(ROOT)}: {url}?v={ver}")
    assert leftovers == []


def test_asset_rev_follows_file_bytes(tmp_path, monkeypatch):
    monkeypatch.delenv("LOVKTV_ASSET_REV", raising=False)
    reset_asset_rev_cache()
    (tmp_path / "a.js").write_text("export const n = 1;\n", encoding="utf-8")
    first = asset_rev(tmp_path)
    (tmp_path / "a.js").write_text("export const n = 2;\n", encoding="utf-8")
    reset_asset_rev_cache()
    second = asset_rev(tmp_path)
    assert first != second
    assert len(first) == 12


def test_frontend_dist_manifest_is_single_source_for_web_and_embedded(tmp_path, monkeypatch):
    source = ROOT
    output = tmp_path / "frontend-dist"
    monkeypatch.delenv("LOVKTV_ASSET_REV", raising=False)
    module = runpy.run_path(str(BUILD))
    manifest = module["build"](source, output)
    disk = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["revision"] == disk["revision"]
    assert manifest["content_sha256"] == _compute(output)
    assert manifest["revision"] == asset_rev(output)
    assert manifest["content_sha256"].startswith(manifest["revision"])
    assert manifest["git_commit"]
    for entry in ("index.html", "m.html", "tv.html", "phone/app.js", "tv/app.js"):
        assert entry in manifest["files"]
        assert (output / entry).is_file()

    # The public URL and the embedded TV URL both resolve to the same entry
    # bytes and revision-bearing module references.
    assert (output / "tv.html").read_text(encoding="utf-8")
    from lovktv.assets import versioned_response

    response = versioned_response(output / "tv.html", output)
    assert f"?v={manifest['revision']}".encode() in response.body


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.setenv("LOVKTV_ASSET_REV", "testhash")
    reset_asset_rev_cache()
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main


def test_pages_inject_same_rev_into_html_and_modules(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        phone = client.get("/m.html")
        tv = client.get("/tv.html")
        landing = client.get("/")
        app_js = client.get("/phone/app.js")
        mix_js = client.get("/tv/playback/js/mix.js")
        aec_js = client.get("/shared/audio/js/aec.js")
        css = client.get("/phone/shell/css/shell.css")
        host = client.get("/api/host")
        manifest = client.get("/manifest.json")

    assert phone.status_code == 200
    assert 'src="/phone/app.js?v=testhash"' in phone.text
    assert 'href="/phone/desk/css/desk.css?v=testhash"' in phone.text
    assert phone.headers["cache-control"].startswith("no-store")
    assert 'src="/tv/app.js?v=testhash"' in tv.text
    assert "/landing/css/landing.css?v=testhash" in landing.text
    assert 'import "./install.js?v=testhash"' in app_js.text
    assert 'from "../shared/i18n/js/i18n.js?v=testhash"' in app_js.text
    assert app_js.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert css.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert host.status_code == 200
    assert host.json()["asset_rev"] == "testhash"
    assert manifest.status_code in {200, 404}
    if manifest.status_code == 200:
        assert manifest.headers["cache-control"].startswith("no-store")
    assert "mediaRevFor" in mix_js.text
    assert "ja-kanji" not in mix_js.text
    assert "stem2" not in mix_js.text
    assert 'addModule("/shared/audio/js/aec/worklet.js?v=testhash")' in aec_js.text
