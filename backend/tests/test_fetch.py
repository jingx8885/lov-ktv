from lovktv.catalog import fetch


def test_clean_search_title_strips_version_marks():
    assert fetch.clean_search_title("晴天(深情版)") == "晴天"
    assert fetch.clean_search_title("晴天 (原唱 周杰伦)") == "晴天"
    assert fetch.clean_search_title("群青 (Remix)") == "群青"


def _no_mugen(monkeypatch):
    monkeypatch.setattr(
        fetch,
        "search_mugen",
        lambda query, count=10, page=1: {"hits": [], "has_more": False, "total": 0},
    )
    monkeypatch.setattr(fetch, "is_mugen_kid", lambda value: False)
    monkeypatch.setattr(fetch, "fetch_kugou_lyrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetch, "pick_bilibili_mv", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetch, "try_bilibili_download", lambda *args, **kwargs: False)
    monkeypatch.setattr(fetch, "search_bilibili_hits", lambda *args, **kwargs: [])
    monkeypatch.setattr(fetch, "search_ytdlp_hits", lambda *args, **kwargs: [])


def test_import_uses_pinned_netease_id(tmp_path, monkeypatch):
    _no_mugen(monkeypatch)
    monkeypatch.setattr(
        fetch,
        "search_tonzhon",
        lambda query, count=12, source="netease", page=1: [
            {"id": "111", "name": "Wrong song", "artist": ["X"]}
        ],
    )
    monkeypatch.setattr(
        fetch,
        "fetch_lyric",
        lambda song_id, source="netease": "[00:01.00]Give a reason",
    )
    downloaded: list[str] = []

    def fake_download(song_id: str, out_path):
        downloaded.append(song_id)
        out_path.write_bytes(b"x" * 60_000)
        return True

    monkeypatch.setattr(fetch, "try_netease_download", fake_download)
    monkeypatch.setattr(
        fetch, "try_ytdlp_search", lambda *args, **kwargs: (False, "should not run")
    )
    skeleton = fetch.import_song(
        query="Give a reason", out_dir=tmp_path, song_id="22689669"
    )
    assert skeleton["source"]["netease_id"] == "22689669"
    assert downloaded == ["22689669"]
    assert (tmp_path / "original.mp3").exists()


def test_import_uses_previewed_ytdlp_page(tmp_path, monkeypatch):
    _no_mugen(monkeypatch)
    fetch._AUDIO_CACHE.clear()
    monkeypatch.setattr(fetch, "search_tonzhon", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        fetch,
        "fetch_lyric",
        lambda song_id, source="netease": "[00:01.00]Give a reason",
    )
    monkeypatch.setattr(fetch, "try_netease_download", lambda song_id, path: False)
    downloaded: list[str] = []
    monkeypatch.setattr(
        fetch,
        "_ytdlp_download",
        lambda page, path: (
            downloaded.append(page) or path.write_bytes(b"x" * 60_000) or True
        ),
    )
    fetch.remember_audio_source(
        "22689669",
        {
            "kind": "ytdlp",
            "page": "https://soundcloud.com/right-track",
            "title": "Give a reason",
            "provider": "soundcloud",
        },
    )
    skeleton = fetch.import_song(
        query="give a reason", out_dir=tmp_path, song_id="22689669"
    )
    assert downloaded == ["https://soundcloud.com/right-track"]
    assert skeleton["audio"]["source"] == "soundcloud"


def test_search_hits_include_preview_url(monkeypatch):
    _no_mugen(monkeypatch)
    seen = {}

    def fake_bili(query, count=8, page=1):
        seen["page"] = page
        seen["count"] = count
        return [
            {
                "id": "BV1xx",
                "title": "Give a reason",
                "artist": "林原めぐみ",
                "source": "bilibili",
                "is_mv": True,
                "preview_url": "/api/preview/BV1xx",
            }
        ]

    monkeypatch.setattr(fetch, "search_bilibili_hits", fake_bili)
    result = fetch.search_songs("Give a reason", count=8, page=2)
    assert result["hits"][0]["preview_url"] == "/api/preview/BV1xx"
    assert result["page"] == 2
    assert result["has_more"] is False
    assert seen == {"page": 2, "count": 8}


def test_search_has_more_when_page_is_full(monkeypatch):
    _no_mugen(monkeypatch)
    monkeypatch.setattr(
        fetch,
        "search_bilibili_hits",
        lambda query, count=10, page=1: [
            {
                "id": f"BV{i}",
                "title": f"song {i}",
                "artist": "a",
                "source": "bilibili",
                "is_mv": True,
            }
            for i in range(count)
        ],
    )
    result = fetch.search_songs("x", count=10, page=1)
    assert result["has_more"] is True
    assert len(result["hits"]) == 10
