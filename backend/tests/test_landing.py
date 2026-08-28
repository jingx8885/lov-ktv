from pathlib import Path

from fastapi.testclient import TestClient


HTML = (Path(__file__).resolve().parents[2] / "frontend" / "public" / "index.html").read_text(encoding="utf-8")
CSS = (Path(__file__).resolve().parents[2] / "frontend" / "public" / "landing" / "css" / "landing.css").read_text(encoding="utf-8")


def test_landing_has_hooks_and_product_exits():
    assert "任意一首歌" in HTML
    assert "当场变成包厢" in HTML
    assert "搜歌名" in HTML
    assert 'href="/tv.html"' in HTML
    assert 'href="/m.html"' in HTML
    assert 'id="opening"' in HTML
    assert 'id="ritual"' in HTML
    assert 'id="features"' in HTML
    assert 'id="house"' in HTML
    assert 'id="notes"' in HTML
    assert "landing.css" in HTML


def test_landing_follows_gigglecut_layout():
    assert "lp-wrap" in CSS
    assert "80rem" in CSS
    assert "lp-trust" in CSS
    assert "lp-features" in CSS
    assert "lp-hero-grid" in CSS
    assert "lp-mesh" in CSS
    assert "lp-beams" in CSS
    assert "lp-lamp" in CSS
    assert "wipe" in CSS
    assert "Inter" in CSS


def test_root_serves_landing(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    with TestClient(main.app) as client:
        page = client.get("/")
    assert page.status_code == 200
    assert "当场变成包厢" in page.text
    assert "/landing/css/landing.css" in page.text
