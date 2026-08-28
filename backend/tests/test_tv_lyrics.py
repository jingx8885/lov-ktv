from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_lyrics_are_smaller_than_shared_defaults():
    shared = (ROOT / "shared" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    tv = (ROOT / "tv" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "clamp(28px, 4.6vw, 58px)" in shared
    assert "clamp(28px, 4.6vw, 58px)" not in tv
    assert "body.tv .lyrics .line" in tv
    assert "clamp(22px, 2.6vw, 38px)" in tv
    assert "clamp(13px, 1.5vw, 20px)" in tv
    assert 'body.tv[data-lyric-mode="all"] .lyrics .line .rt { display: none; }' in tv
    assert 'href="/tv/lyrics/css/lyrics.css' in html
