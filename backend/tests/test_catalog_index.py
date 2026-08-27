from lovktv.catalog.index import first_letter, prefer_native_library, query_library, song_letter, song_matches


def test_first_letter_latin_han_kana():
    assert first_letter("NIGHT DANCER") == "N"
    assert first_letter("So Sick") == "S"
    assert first_letter("群青") == "Q"
    assert first_letter("真夜中のドア") == "Z"
    assert first_letter("123 intro") == "#"
    assert first_letter("のドア") == "N"


def test_song_letter_uses_title_or_artist():
    song = {"title": "群青 · YOASOBI", "artist": "YOASOBI"}
    assert song_letter(song, "title") == "Q"
    assert song_letter(song, "artist") == "Y"


def test_song_matches_title_and_artist():
    song = {"title": "So Sick · Ne-Yo", "artist": "Ne-Yo"}
    assert song_matches(song, "sick", "title")
    assert song_matches(song, "ne-yo", "artist")
    assert not song_matches(song, "ne-yo", "title")
    assert song_matches(song, "ne-yo", "all")


def test_prefer_native_library_hides_composed_duplicates():
    songs = [
        {"id": "old", "title": "群青 · YOASOBI", "artist": "YOASOBI", "audio_source": "soundcloud"},
        {"id": "mv", "title": "群青 · YOASOBI", "artist": "YOASOBI", "audio_source": "mugen", "native_video": True},
        {"id": "keep", "title": "So Sick · Ne-Yo", "artist": "Ne-Yo", "audio_source": "netease"},
    ]
    kept = prefer_native_library(songs)
    assert [song["id"] for song in kept] == ["mv", "keep"]


def test_query_library_filters_letter_and_pages():
    songs = [
        {"id": "1", "title": "NIGHT DANCER · imase", "artist": "imase"},
        {"id": "2", "title": "群青 · YOASOBI", "artist": "YOASOBI"},
        {"id": "3", "title": "So Sick · Ne-Yo", "artist": "Ne-Yo"},
        {"id": "4", "title": "Give a reason", "artist": "奥井雅美"},
        {"id": "5", "title": "Get along", "artist": "林原めぐみ"},
    ]
    page = query_library(songs, letter="G", count=1, page=1)
    assert page["total"] == 2
    assert page["pages"] == 2
    assert page["songs"][0]["title"].startswith("Get")
    next_page = query_library(songs, letter="G", count=1, page=2)
    assert next_page["songs"][0]["title"].startswith("Give")

    artist = query_library(songs, q="yoasobi", by="artist")
    assert [row["id"] for row in artist["songs"]] == ["2"]
    assert artist["letters"][0]["key"] == "Y"

    titled = query_library(songs, q="night", by="title")
    assert titled["total"] == 1
    assert titled["songs"][0]["letter"] == "N"
