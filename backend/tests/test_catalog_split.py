from lovktv.catalog import audio, importer, lyrics, search


def test_catalog_modules_have_single_responsibilities():
    assert search.clean_search_title is not lyrics.parse_lrc
    assert importer.import_song is not audio.resolve_audio_source


def test_parse_lrc_ignores_malformed_and_metadata_lines():
    assert lyrics.parse_lrc("bad\n[00:01.00]作词：甲\n[00:02.00]hello") == [
        {"ms": 2000, "text": "hello"}
    ]


def test_audio_cache_roundtrip_keeps_copy_semantics():
    audio._AUDIO_CACHE.clear()
    audio.remember_audio_source("id", {"kind": "ytdlp", "page": "x"})
    value = audio.peek_audio_source("id")
    value["page"] = "changed"
    assert audio.peek_audio_source("id")["page"] == "x"
    audio.forget_audio_source("id")
    assert audio.peek_audio_source("id") == {}
