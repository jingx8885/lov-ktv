from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_library_append_dedupes_and_poll_does_not_rewind_page():
    lib = (ROOT / "phone" / "desk" / "js" / "library.js").read_text(encoding="utf-8")
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    hits = (ROOT / "phone" / "search" / "js" / "hits.js").read_text(encoding="utf-8")
    assert "function knownLibIds" in lib
    assert "function libSongId" in lib
    assert 'params.set("after", after)' in lib
    assert "id !== after" in lib
    assert 'data-song="${escapeHtml(song.id)}"' in lib
    assert "if (state.libState.page <= 1) loadSongs(false)" in app
    html = (ROOT / "m.html").read_text(encoding="utf-8")
    assert 'id="libRefresh"' in html
    assert "phone.desk.refresh" in html
    assert 'cache: "no-store"' in lib
    assert "loadSongs(false, true)" in lib
    assert "extra.length > 0" in hits
    assert "data.page !== state.searchPage" in hits
    assert "btn.onclick = () => runSearch(Number(btn.dataset.page), true)" not in hits
