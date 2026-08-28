from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_lyrics_use_this_morning_small_type():
    shared = (ROOT / "shared" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    tv = (ROOT / "tv" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "clamp(28px, 4.6vw, 58px)" in shared
    assert "font-size: .62em" in shared
    assert "clamp(18px, 5.6vw, 26px)" in tv
    assert "font-size: 13px" in tv
    assert "font-size: .28em" in tv
    assert "font-size: .26em" in tv
    assert "font-size: 0.42em" in tv
    assert "font-size: .62em" not in tv
    assert 'href="/tv/lyrics/css/lyrics.css?v=split6"' in html


def test_tv_page_has_no_language_picker():
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "lang-picker" not in html
    assert "data-set-lang" not in html
