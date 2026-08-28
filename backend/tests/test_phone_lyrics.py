from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_lyric_mode_buttons_do_not_select_body():
    mix = (ROOT / "phone" / "room" / "js" / "mix.js").read_text(encoding="utf-8")
    paint = (ROOT / "shared" / "lyrics" / "js" / "paint.js").read_text(encoding="utf-8")
    assert 'el.dataset.lyricMode = mode' in paint
    assert 'querySelectorAll("[data-lyric-mode]")' not in mix
    assert 'querySelectorAll("button[data-lyric-mode]")' in mix
    assert mix.count('querySelectorAll("button[data-lyric-mode]")') >= 2
    assert "btn.textContent = jaLabel" in mix
    assert 'if (!room || !hostVol' in mix
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "m.html").read_text(encoding="utf-8")
    assert 'getElementById("page-desk")' in app
    assert '$must("page-desk")' not in app
    assert "mix.js?v=mix2" in app
    assert 'src="/phone/app.js?v=split18"' in html
