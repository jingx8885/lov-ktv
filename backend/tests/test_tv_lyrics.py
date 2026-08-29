from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_lyrics_use_this_morning_small_type():
    shared = (ROOT / "shared" / "lyrics" / "css" / "lyrics.css").read_text(
        encoding="utf-8"
    )
    tv = (ROOT / "tv" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    stage = (ROOT / "tv" / "stage" / "css" / "stage.css").read_text(encoding="utf-8")
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "clamp(28px, 4.6vw, 58px)" in shared
    assert "font-size: 0.34em" in shared
    assert "font-size: .62em" in shared
    assert "font-size: 17px !important" in tv
    assert "font-size: 11px !important" in tv
    assert "clamp(" not in tv
    assert "font-size: 42px" not in tv
    assert "clamp(18px, 2.8vw, 34px)" not in tv
    assert "position: absolute" in stage
    assert "bottom: 28px" in stage
    assert "body.tv .lyrics .anno .rt" in tv
    assert "body.tv .lyrics .anno .roma" in tv
    assert "body.tv .lyrics .anno .gloss" in tv
    assert "font-size: 12px !important" in tv
    assert "font-size: 13px !important" in tv
    assert "font-size: 14px" not in tv
    assert "font-size: 15px" not in tv
    assert "font-size: .28em" not in tv
    assert "font-size: .62em" not in tv
    assert "backdrop-filter" not in tv
    assert "drop-shadow" not in tv
    assert 'href="/tv/lyrics/css/lyrics.css"' in html
    assert 'href="/shared/lyrics/css/lyrics.css"' in html
    assert 'class="tv is-waiting"' in html
    assert 'src="/brand/wait-tv.jpg"' in html
    assert "body.tv.is-waiting .lyric-plate" in tv
    assert "body.tv.is-waiting .lyric-plate" in shared
    assert "body.tv.is-waiting .wait-art" in stage
    assert 'href="/tv/stage/css/stage.css"' in html
    assert "min-height: 12px" in tv
    assert "min-height: 13px" in tv
    paint = (ROOT / "shared" / "lyrics" / "js" / "paint.js").read_text(encoding="utf-8")
    assert "function tvStage()" in paint
    assert "if (tvStage()) return;" in paint
    assert "transform: none !important" in tv


def test_tv_page_has_no_language_picker():
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "lang-picker" not in html
    assert "data-set-lang" not in html
