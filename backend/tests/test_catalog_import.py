from lovktv.catalog import audio, importer, search


def test_sync_video_to_audio_trims_or_loops_to_mp3(tmp_path, monkeypatch):
    video = tmp_path / "mtv.mp4"
    audio_path = tmp_path / "original.mp3"
    video.write_bytes(b"video")
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    durations = {video: 5_000, audio_path: 8_000}
    monkeypatch.setattr("lovktv.pipeline.audio.probe_duration_ms", lambda path: durations[path])

    def fake_run(cmd, **kwargs):
        from pathlib import Path

        Path(cmd[-1]).write_bytes(b"synced-video" * 200)

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    assert audio.sync_video_to_audio(video, audio_path)
    assert video.read_bytes() == b"synced-video" * 200


def test_complete_mugen_audio_syncs_existing_media_fast_path(tmp_path, monkeypatch):
    mp3 = tmp_path / "original.mp3"
    mtv = tmp_path / "mtv.mp4"
    mp3.write_bytes(b"a" * 500)
    mtv.write_bytes(b"v" * 500)
    calls = []
    monkeypatch.setattr(importer, "sync_video_to_audio", lambda video, audio: calls.append((video, audio)) or True)
    skeleton = {"audio": {"file": "original.mp3"}, "has_video": True}
    assert importer._complete_mugen_audio(skeleton, tmp_path, "song") is skeleton
    assert calls == [(mtv, mp3)]


def test_duration_match_classifies_and_scores():
    exact = search.annotate_duration_match({"duration": 180, "lyrics_duration": 180})
    assert exact["duration_match"] == "exact"
    assert exact["lyrics_match"] == "exact"
    assert exact["lyrics_match_score"] == 100
    close = search.annotate_duration_match({"duration": 180, "lyrics_duration": 174})
    assert close["duration_match"] == "close"
    assert close["duration_match_score"] == 1
    assert close["lyrics_match_score"] == 97
    mismatch = search.annotate_duration_match({"duration": 180, "lyrics_duration": 120})
    assert mismatch["duration_match"] == "mismatch"
    assert mismatch["duration_match_score"] == -1
    assert mismatch["lyrics_match_score"] == 67


def test_lyric_match_status_is_explicit_when_duration_is_unknown():
    assert search.annotate_duration_match({"lyrics_ready": True})["lyrics_match"] == "available"
    assert search.annotate_duration_match({"lyrics_ready": False})["lyrics_match"] == "none"
    assert search.annotate_duration_match({})["lyrics_match"] == "unknown"


def test_search_ranks_late_exact_hit_before_unknowns(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_mugen",
        lambda *args, **kwargs: {
            "hits": [
                {"id": "m1", "title": "Unknown 1", "source": "mugen"},
                {"id": "m2", "title": "Unknown 2", "source": "mugen"},
            ],
            "has_more": False,
        },
    )
    monkeypatch.setattr(
        search,
        "search_bilibili_hits",
        lambda *args, **kwargs: [
            {"id": "b1", "title": "Exact", "source": "bilibili", "duration": 180, "lyrics_duration": 180}
        ],
    )
    monkeypatch.setattr(search, "search_ytdlp_hits", lambda *args, **kwargs: [])
    result = search.search_songs("Exact", count=2)
    assert result["hits"][0]["id"] == "b1"
    assert len(result["hits"]) == 2


def test_clean_search_title_strips_version_marks():
    assert search.clean_search_title("晴天(深情版)") == "晴天"
    assert search.clean_search_title("晴天 (原唱 周杰伦)") == "晴天"
    assert search.clean_search_title("群青 (Remix)") == "群青"


def _no_mugen(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_mugen",
        lambda query, count=10, page=1: {"hits": [], "has_more": False, "total": 0},
    )
    monkeypatch.setattr(importer, "is_mugen_kid", lambda value: False)
    monkeypatch.setattr(importer, "fetch_kugou_lyrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(importer, "pick_bilibili_mv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        importer, "try_bilibili_download", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(search, "search_bilibili_hits", lambda *args, **kwargs: [])
    monkeypatch.setattr(search, "search_ytdlp_hits", lambda *args, **kwargs: [])


def test_import_uses_pinned_netease_id(tmp_path, monkeypatch):
    _no_mugen(monkeypatch)
    monkeypatch.setattr(
        importer,
        "search_tonzhon",
        lambda query, count=12, source="netease", page=1: [
            {"id": "111", "name": "Wrong song", "artist": ["X"]}
        ],
    )
    monkeypatch.setattr(
        importer,
        "fetch_lyric",
        lambda song_id, source="netease": "[00:01.00]Give a reason",
    )
    downloaded: list[str] = []

    def fake_download(song_id: str, out_path):
        downloaded.append(song_id)
        out_path.write_bytes(b"x" * 60_000)
        return True

    monkeypatch.setattr(importer, "try_netease_download", fake_download)
    monkeypatch.setattr(
        importer, "try_ytdlp_search", lambda *args, **kwargs: (False, "should not run")
    )
    skeleton = importer.import_song(
        query="Give a reason", out_dir=tmp_path, song_id="22689669"
    )
    assert skeleton["source"]["netease_id"] == "22689669"
    assert downloaded == ["22689669"]
    assert (tmp_path / "original.mp3").exists()


def test_import_uses_previewed_ytdlp_page(tmp_path, monkeypatch):
    _no_mugen(monkeypatch)
    audio._AUDIO_CACHE.clear()
    monkeypatch.setattr(importer, "search_tonzhon", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        importer,
        "fetch_lyric",
        lambda song_id, source="netease": "[00:01.00]Give a reason",
    )
    monkeypatch.setattr(importer, "try_netease_download", lambda song_id, path: False)
    downloaded: list[str] = []
    monkeypatch.setattr(
        importer,
        "_ytdlp_download",
        lambda page, path: (
            downloaded.append(page) or path.write_bytes(b"x" * 60_000) or True
        ),
    )
    audio.remember_audio_source(
        "22689669",
        {
            "kind": "ytdlp",
            "page": "https://soundcloud.com/right-track",
            "title": "Give a reason",
            "provider": "soundcloud",
        },
    )
    skeleton = importer.import_song(
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

    monkeypatch.setattr(search, "search_bilibili_hits", fake_bili)
    result = search.search_songs("Give a reason", count=8, page=2)
    assert result["hits"][0]["preview_url"] == "/api/preview/BV1xx"
    assert result["page"] == 2
    assert result["has_more"] is False
    assert seen == {"page": 2, "count": 8}


def test_search_has_more_when_page_is_full(monkeypatch):
    _no_mugen(monkeypatch)
    monkeypatch.setattr(
        search,
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
    result = search.search_songs("x", count=10, page=1)
    assert result["has_more"] is True
    assert len(result["hits"]) == 10
