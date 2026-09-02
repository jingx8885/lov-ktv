import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_lyric_mode_buttons_do_not_select_body():
    mix = (ROOT / "phone" / "room" / "js" / "room" / "mix.js").read_text(
        encoding="utf-8"
    )
    paint = (ROOT / "shared" / "lyrics" / "js" / "paint.js").read_text(encoding="utf-8")
    assert "el.dataset.lyricMode = mode" in paint
    assert "function tokenRoma" in paint
    assert "export function lyricScript" in paint
    assert "export function lyricModeForScript" in paint
    assert 'querySelectorAll("[data-lyric-mode]")' not in mix
    assert 'querySelectorAll("button[data-lyric-mode]")' in mix
    assert mix.count('querySelectorAll("button[data-lyric-mode]")') >= 2
    assert "export { lyricModeForScript, lyricScript }" in mix
    assert 'btn.hidden = key === "roma"' in mix
    assert "if (!room || !hostVol" in mix
    assert "keepRoma" in paint
    assert "keepGloss" in paint
    assert "keepZh" in paint
    assert "keepRt" in paint
    assert "export function sanitizeLyrics" in paint
    song = (ROOT / "phone" / "player" / "js" / "playback" / "song.js").read_text(
        encoding="utf-8"
    )
    assert "sanitizeLyrics(lyrics.data)" in song
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "m.html").read_text(encoding="utf-8")
    assert 'getElementById("page-desk")' in app
    assert '$must("page-desk")' not in app
    assert 'from "./room/js/room/mix.js"' in app
    assert 'from "../../../../shared/lyrics/js/paint.js"' in mix
    assert 'src="/phone/app.js"' in html
    assert 'href="/phone/desk/css/desk.css"' in html
    assert 'from "./player/js/playback/mic.js"' in app
    css = (ROOT / "phone" / "player" / "css" / "player.css").read_text(encoding="utf-8")
    mic = (ROOT / "phone" / "player" / "js" / "playback" / "mic.js").read_text(
        encoding="utf-8"
    )
    assert ".player-dock.is-hint .player-hint" in css
    assert re.search(r"\.player-hint\[data-hold\]\s*\{\s*display:\s*block;\s*\}", css)
    assert 'btn.classList.add("busy")' in mic
    assert "btn.disabled = true" not in mic
    for name in ("zh", "yue", "en", "ja"):
        loc = (ROOT / "shared" / "i18n" / "locales" / f"{name}.js").read_text(
            encoding="utf-8"
        )
        assert '"phone.mic.opened"' in loc


def test_english_lyric_labels_are_not_abbreviated():
    en = (ROOT / "shared" / "i18n" / "locales" / "en.js").read_text(encoding="utf-8")
    assert '"phone.lyric.src": "Lyrics"' in en
    assert '"phone.lyric.zh": "中译"' in en
    assert '"phone.lyric.roma": "Romaji"' in en
    assert '"phone.lyric.src": "Orig"' not in en
    assert '"phone.lyric.roma": "Roma"' not in en
