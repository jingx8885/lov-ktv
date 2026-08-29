from lovktv.catalog import fetch
from lovktv.catalog import search, lyrics, audio, importer


def test_fetch_facade_exports_split_implementations():
    assert fetch.clean_search_title is search.clean_search_title
    assert fetch.parse_lrc is lyrics.parse_lrc
    assert fetch._AUDIO_CACHE is audio._AUDIO_CACHE
    assert fetch.import_song is importer.import_song


def test_parse_lrc_ignores_malformed_and_metadata_lines():
    assert fetch.parse_lrc("bad\n[00:01.00]作词：甲\n[00:02.00]hello") == [
        {"ms": 2000, "text": "hello"}
    ]


def test_audio_cache_roundtrip_keeps_copy_semantics():
    fetch._AUDIO_CACHE.clear()
    fetch.remember_audio_source("id", {"kind": "ytdlp", "page": "x"})
    value = fetch.peek_audio_source("id")
    value["page"] = "changed"
    assert fetch.peek_audio_source("id")["page"] == "x"
    fetch.forget_audio_source("id")
    assert fetch.peek_audio_source("id") == {}
