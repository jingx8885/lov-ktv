from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_library_append_dedupes_and_poll_does_not_rewind_page():
    lib = (ROOT / "phone" / "desk" / "js" / "library.js").read_text(encoding="utf-8")
    app = (ROOT / "phone" / "app.js").read_text(encoding="utf-8")
    hits = (ROOT / "phone" / "search" / "js" / "hits.js").read_text(encoding="utf-8")
    assert "function knownLibIds" in lib
    assert "song.id && !seen.has(song.id)" in lib
    assert 'data-song="${escapeHtml(song.id)}"' in lib
    assert "if (state.libState.page <= 1) loadSongs(false)" in app
    assert "extra.length > 0" in hits
    assert "data.page !== state.searchPage" in hits
    assert 'btn.onclick = () => runSearch(Number(btn.dataset.page), true)' not in hits
