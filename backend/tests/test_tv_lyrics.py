from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_lyrics_use_this_morning_small_type():
    shared = (ROOT / "shared" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    tv = (ROOT / "tv" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "clamp(28px, 4.6vw, 58px)" in shared
    assert "font-size: .62em" in shared
    assert "clamp(13px, 3.6vw, 17px)" in tv
    assert "font-size: 11px" in tv
    assert "body.tv .lyrics .anno .roma" in tv
    assert "body.tv .lyrics .anno .gloss" in tv
    assert "font-size: 14px" in tv
    assert "font-size: 15px" in tv
    assert "font-size: .28em" not in tv
    assert "font-size: .62em" not in tv
    assert 'href="/tv/lyrics/css/lyrics.css?v=split10"' in html
    assert "min-height: 1.15em" in tv
    assert "min-height: 1.2em" in tv


def test_tv_page_has_no_language_picker():
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "lang-picker" not in html
    assert "data-set-lang" not in html
