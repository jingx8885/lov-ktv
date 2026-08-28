from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_lyric_mode_buttons_do_not_select_body():
    mix = (ROOT / "phone" / "room" / "js" / "mix.js").read_text(encoding="utf-8")
    paint = (ROOT / "shared" / "lyrics" / "js" / "paint.js").read_text(encoding="utf-8")
    assert 'el.dataset.lyricMode = mode' in paint
    assert "function tokenRoma" in paint
    assert "export function lyricScript" in paint
    assert "export function lyricModeForScript" in paint
    assert 'querySelectorAll("[data-lyric-mode]")' not in mix
    assert 'querySelectorAll("button[data-lyric-mode]")' in mix
    assert mix.count('querySelectorAll("button[data-lyric-mode]")') >= 2
    assert "export { lyricModeForScript, lyricScript }" in mix
    assert 'btn.hidden = key === "roma"' in mix
    assert 'if (!room || !hostVol' in mix
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "m.html").read_text(encoding="utf-8")
    assert 'getElementById("page-desk")' in app
    assert '$must("page-desk")' not in app
    assert "mix.js?v=mix4" in app
    assert "paint.js?v=paint2" in mix
    assert 'src="/phone/app.js?v=split21"' in html
    assert 'href="/phone/desk/css/desk.css?v=split9"' in html


def test_english_lyric_labels_are_not_abbreviated():
    en = (ROOT / "shared" / "i18n" / "locales" / "en.js").read_text(encoding="utf-8")
    assert '"phone.lyric.src": "Lyrics"' in en
    assert '"phone.lyric.zh": "中译"' in en
    assert '"phone.lyric.roma": "Romaji"' in en
    assert '"phone.lyric.src": "Orig"' not in en
    assert '"phone.lyric.roma": "Roma"' not in en
