from pathlib import Path

from lovktv.catalog import importer, mugen, search
from lovktv.workers import jobs

ASS = """\ufeff[Script Info]
Title: NIGHT DANCER

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Comment: 0,0:00:00.00,0:00:00.00,Ao,,0,0,0,template pre-line all keeptags,ignore
Comment: 0,0:00:02.07,0:00:05.69,Hajime,,0,0,0,karaoke,{\\k54}dou {\\k24}de{\\k25}mo {\\k28}i{\\k27}i
Dialogue: 0,0:03:11.97,0:03:16.54,groupe,,0,0,0,fx,{\\k90\\fad(300,200)}{\\k48}dou {\\k27}de{\\k27}mo {\\k26}i{\\k25}i
Dialogue: 0,0:03:15.76,0:03:20.26,groupe,,0,0,0,fx,{\\k90\\fad(300,200)}{\\k29}fu{\\k26}ra{\\k25}tsu
"""


def test_pick_title_prefers_japanese_over_romaji():
    assert (
        mugen.pick_title(
            {
                "titles": {"eng": "Gunjou", "qro": "Gunjô", "jpn": "群青"},
                "titles_default_language": "eng",
                "songname": "Gunjou",
            }
        )
        == "群青"
    )


def test_install_video_encodes_av1(tmp_path, monkeypatch):
    src = tmp_path / "clip.webm"
    dest = tmp_path / "mtv.mp4"
    src.write_bytes(b"x")
    calls = []

    def fake_ffmpeg(*args, timeout=300):
        calls.append((args, timeout))
        dest.write_bytes(b"v" * 2000)

    monkeypatch.setattr(mugen, "video_codec", lambda path: "av1")
    monkeypatch.setattr(mugen, "_ffmpeg", fake_ffmpeg)
    assert mugen.install_video(src, dest)
    assert "libx264" in calls[0][0]


def test_install_video_copies_h264_mp4(tmp_path, monkeypatch):
    src = tmp_path / "clip.mp4"
    dest = tmp_path / "mtv.mp4"
    src.write_bytes(b"v" * 2000)
    monkeypatch.setattr(mugen, "video_codec", lambda path: "h264")
    monkeypatch.setattr(
        mugen,
        "_ffmpeg",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("copy h264")),
    )
    assert mugen.install_video(src, dest)
    assert dest.read_bytes() == src.read_bytes()


def test_finish_ready_lyrics_marks_native_video(tmp_path, monkeypatch):
    out_dir = tmp_path / "s1"
    out_dir.mkdir()
    (out_dir / "mugen.mp4").write_bytes(b"v" * 2000)
    (out_dir / "mtv.mp4").write_bytes(b"v" * 2000)
    (out_dir / "lyrics.json").write_text(
        '{"language":"en","alignment_source":"karaoke-mugen","cues":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "get_song", lambda sid: {"title": "x", "artist": "y"})
    monkeypatch.setattr(
        jobs,
        "compose_mtv",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("keep mv")),
    )
    jobs._finish_ready_lyrics(
        "s1", out_dir, out_dir / "mtv.mp4", "en", rebuild_mtv=False
    )
    timeline = __import__("json").loads(
        (out_dir / "lyrics.json").read_text(encoding="utf-8")
    )
    assert timeline["native_video"] is True


def test_finish_ready_lyrics_keeps_composed_mtv_off_native(tmp_path, monkeypatch):
    out_dir = tmp_path / "s2"
    out_dir.mkdir()
    (out_dir / "mtv.mp4").write_bytes(b"v" * 2000)
    (out_dir / "lyrics.json").write_text(
        '{"language":"en","alignment_source":"karaoke-mugen","cues":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "get_song", lambda sid: {"title": "x", "artist": "y"})
    monkeypatch.setattr(jobs, "compose_mtv", lambda *args, **kwargs: None)
    jobs._finish_ready_lyrics(
        "s2", out_dir, out_dir / "mtv.mp4", "en", rebuild_mtv=False
    )
    timeline = __import__("json").loads(
        (out_dir / "lyrics.json").read_text(encoding="utf-8")
    )
    assert timeline.get("native_video") is not True


def test_parse_ass_uses_dialogue_karaoke_timing():
    cues = mugen.parse_ass(ASS)
    assert [cue["text"] for cue in cues] == ["dou demo ii", "furatsu"]
    first = cues[0]
    assert first["start_ms"] == 3 * 60_000 + 11_970 + 900
    assert first["tokens"][0]["text"] == "dou "
    assert first["tokens"][0]["end_ms"] - first["tokens"][0]["start_ms"] == 480


def test_parse_ass_falls_back_to_comment_karaoke():
    raw = """
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,no karaoke here
Comment: 0,0:00:02.07,0:00:05.69,Hajime,,0,0,0,karaoke,{\\k54}hello {\\k20}world
"""
    cues = mugen.parse_ass(raw)
    assert cues[0]["text"] == "hello world"
    assert cues[0]["tokens"][0]["start_ms"] == 2070


def test_timeline_from_ass_merges_english_syllables_into_words():
    raw = r"""
Comment: 0,0:00:02.07,0:00:03.00,Hajime,,0,0,0,karaoke,{\k20}hel{\k30}lo {\k15}wor{\k25}ld!
"""
    timeline = mugen.timeline_from_ass(raw, "en")
    assert [token["text"] for token in timeline["cues"][0]["tokens"]] == [
        "hello ",
        "world!",
    ]
    assert timeline["cues"][0]["tokens"][0]["start_ms"] == 2070
    assert timeline["cues"][0]["tokens"][0]["end_ms"] == 2570


def test_classify_dual_audio_uses_stream_titles():
    streams = [
        {"index": 0, "codec_type": "video"},
        {"index": 1, "codec_type": "audio", "tags": {"title": "Instrumental"}},
        {"index": 2, "codec_type": "audio", "tags": {"title": "Vocals"}},
    ]
    assert mugen.classify_dual_audio(streams) == {"karaoke": 1, "vocal": 2}


def test_classify_dual_audio_defaults_first_to_karaoke():
    streams = [
        {"index": 1, "codec_type": "audio", "tags": {}},
        {"index": 2, "codec_type": "audio", "tags": {}},
    ]
    assert mugen.classify_dual_audio(streams) == {"karaoke": 1, "vocal": 2}


def test_classify_single_audio_is_none():
    assert mugen.classify_dual_audio([{"index": 1, "codec_type": "audio"}]) is None


def test_is_off_vocal_detects_mugen_songname():
    assert mugen.is_off_vocal("JPN - YOASOBI - MV - Gunjô ~ Off Vocal Vers")
    assert not mugen.is_off_vocal("JPN - YOASOBI - MV - Gunjô")


def test_pick_vocal_hit_skips_off_vocal():
    hits = [
        {"id": "off", "title": "群青", "off_vocal": True},
        {"id": "on", "title": "群青", "off_vocal": False},
    ]
    assert mugen.pick_vocal_hit(hits)["id"] == "on"


def test_map_hit_marks_off_vocal():
    hit = mugen.map_hit(
        {
            "kid": "2e626891-5435-4333-b9bc-90e270f74e8f",
            "titles": {"jpn": "群青"},
            "songname": "JPN - YOASOBI - MV - Gunjô ~ Off Vocal Vers",
            "singers": [{"name": "YOASOBI"}],
            "lyrics_infos": [{"filename": "x.ass"}],
            "mediafile": "x.mp4",
            "duration": 262,
        }
    )
    assert hit["off_vocal"] is True
    assert hit["clean"] is False
    assert hit["title"] == "群青"
    assert hit["preview_url"] == "/api/preview/2e626891-5435-4333-b9bc-90e270f74e8f"
    assert hit["media"] == "x.mp4"


def test_open_mugen_preview_uses_mediafile(monkeypatch):
    opened = []

    class FakeResp:
        headers = {"Content-Type": "video/mp4"}

        def read(self, _n):
            return b""

        def close(self):
            pass

    def fake_urlopen(req, timeout=30):
        opened.append(req.full_url)
        if "/previews/" in req.full_url:
            raise OSError("no short preview")
        return FakeResp()

    monkeypatch.setattr(mugen.urllib.request, "urlopen", fake_urlopen)
    resp = mugen.open_mugen_preview(
        "2e626891-5435-4333-b9bc-90e270f74e8f", media_name="song.mp4"
    )
    assert resp is not None
    assert any(
        url.startswith("https://kara.moe/downloads/medias/") and "song.mp4" in url
        for url in opened
    )


def test_preview_api_accepts_mugen_kid(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from fastapi.testclient import TestClient

    from lovktv import main
    from lovktv.media import host_volume
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    host_volume._cached = None

    class FakeResp:
        headers = {"Content-Type": "video/mp4"}
        _sent = False

        def read(self, _n):
            if self._sent:
                return b""
            self._sent = True
            return b"abc"

        def close(self):
            pass

    from lovktv.routers import songs

    monkeypatch.setattr(
        songs,
        "open_preview_stream",
        lambda *args, **kwargs: (FakeResp(), {"kind": "mugen", "title": "群青"}),
    )
    with TestClient(main.app) as client:
        info = client.get("/api/preview/2e626891-5435-4333-b9bc-90e270f74e8f/resolve")
        assert info.status_code == 200
        assert info.json()["kind"] == "mugen"
        stream = client.get(
            "/api/preview/2e626891-5435-4333-b9bc-90e270f74e8f?media=song.mp4"
        )
        assert stream.status_code == 200
        assert stream.content == b"abc"


def test_search_songs_puts_mugen_first(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_mugen",
        lambda query, count=10, page=1: {
            "hits": [
                {
                    "id": "13393b41-9204-42ca-b014-e548bd60ca9f",
                    "title": "NIGHT DANCER",
                    "artist": "ReGLOSS",
                    "source": "mugen",
                    "lyrics_ready": True,
                    "preview_url": "",
                    "clean": True,
                }
            ],
            "has_more": False,
            "total": 1,
        },
    )
    monkeypatch.setattr(
        search,
        "search_bilibili_hits",
        lambda query, count=8, page=1: [
            {
                "id": "BV1xx",
                "title": "B站兜底",
                "artist": "UP",
                "source": "bilibili",
                "is_mv": True,
            }
        ],
    )
    monkeypatch.setattr(search, "search_ytdlp_hits", lambda *args, **kwargs: [])
    result = search.search_songs("NIGHT DANCER", count=10, page=1)
    assert result["hits"][0]["source"] == "mugen"
    assert result["hits"][0]["title"] == "NIGHT DANCER"
    assert result["hits"][1]["source"] == "bilibili"
    assert result["hits"][0].get("is_mv") is not False
    assert result["hits"][1]["is_mv"] is True
    assert result["has_more"] is False


def test_search_songs_marks_exact_duration_hits_first(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_mugen",
        lambda *args, **kwargs: {
            "hits": [
                {
                    "id": "mugen-exact",
                    "title": "Exact",
                    "source": "mugen",
                    "lyrics_ready": True,
                    "duration": 180,
                }
            ],
            "has_more": False,
        },
    )
    monkeypatch.setattr(
        search,
        "search_bilibili_hits",
        lambda *args, **kwargs: [{"id": "bili", "title": "Other", "source": "bilibili", "duration": 180}],
    )
    monkeypatch.setattr(search, "search_ytdlp_hits", lambda *args, **kwargs: [])
    result = search.search_songs("Exact", count=10, page=1)
    assert result["hits"][0]["duration_match"] == "exact"
    assert result["hits"][0]["duration_match_score"] == 3
    assert result["hits"][0]["lyrics_match"] == "exact"
    assert result["hits"][0]["lyrics_match_score"] == 100


def test_search_songs_queries_channels_together(monkeypatch):
    called = []

    def fake_mugen(query, count=10, page=1):
        called.append("mugen")
        return {
            "hits": [
                {
                    "id": f"kid-{i}",
                    "title": f"MV {i}",
                    "source": "mugen",
                    "is_mv": True,
                }
                for i in range(count)
            ],
            "has_more": True,
            "total": 40,
        }

    def fake_bili(query, count=8, page=1):
        called.append("bilibili")
        return [
            {
                "id": "BV1xx",
                "title": "B站",
                "artist": "UP",
                "source": "bilibili",
                "is_mv": True,
            }
        ]

    monkeypatch.setattr(search, "search_mugen", fake_mugen)
    monkeypatch.setattr(search, "search_bilibili_hits", fake_bili)
    monkeypatch.setattr(search, "search_ytdlp_hits", lambda *args, **kwargs: [])
    result = search.search_songs("群青", count=10, page=1)
    assert set(called) == {"mugen", "bilibili"}
    assert result["hits"][0]["source"] == "mugen"
    assert any(hit["source"] == "bilibili" for hit in result["hits"])
    assert result["has_more"] is True


def test_search_songs_keeps_mugen_when_others_fail(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_mugen",
        lambda query, count=10, page=1: {
            "hits": [{"id": "kid", "title": "群青", "source": "mugen", "is_mv": True}],
            "has_more": False,
            "total": 1,
        },
    )
    monkeypatch.setattr(
        search,
        "search_bilibili_hits",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )
    monkeypatch.setattr(search, "search_ytdlp_hits", lambda *args, **kwargs: [])
    result = search.search_songs("群青", count=10, page=1)
    assert result["hits"][0]["title"] == "群青"
    assert result["hits"][0]["source"] == "mugen"


def test_search_songs_shows_remaining_channels(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_mugen",
        lambda query, count=10, page=1: {
            "hits": [{"id": "kid", "title": "Mugen", "source": "mugen", "is_mv": True}],
            "has_more": False,
            "total": 1,
        },
    )
    monkeypatch.setattr(
        search,
        "search_bilibili_hits",
        lambda query, count=8, page=1: [
            {
                "id": "BV1xx",
                "title": "B站",
                "artist": "UP",
                "source": "bilibili",
                "is_mv": True,
            }
        ],
    )
    monkeypatch.setattr(
        search,
        "search_ytdlp_hits",
        lambda query, provider, count=5, page=1: [
            {
                "id": "soundcloud_abc",
                "title": "sc",
                "artist": "",
                "source": "soundcloud",
                "is_mv": False,
            }
        ],
    )
    result = search.search_songs("晴天", count=10, page=1)
    assert [hit["source"] for hit in result["hits"]] == [
        "mugen",
        "bilibili",
        "soundcloud",
    ]
    assert result["sources"] == ["mugen", "bilibili", "soundcloud"]


def test_import_song_prefers_vocal_mugen_hit(tmp_path, monkeypatch):
    called = {}

    def fake_search(query, count=8, page=1):
        return {
            "hits": [
                {"id": "off-kid", "title": "群青", "off_vocal": True},
                {
                    "id": "88bbec95-58e2-4407-adf2-74d7c6e4ac1d",
                    "title": "群青",
                    "off_vocal": False,
                },
            ]
        }

    def fake_import(kid, out_dir, query=""):
        called["kid"] = kid
        (out_dir / "original.mp3").write_bytes(b"x" * 1000)
        return {"title": "群青", "source": {"provider": "karaoke-mugen", "kid": kid}}

    monkeypatch.setattr(importer, "search_mugen", fake_search)
    monkeypatch.setattr(importer, "import_mugen_song", fake_import)
    importer.import_song(query="群青 YOASOBI", out_dir=tmp_path)
    assert called["kid"] == "88bbec95-58e2-4407-adf2-74d7c6e4ac1d"


def test_import_song_uses_mugen_kid(tmp_path, monkeypatch):
    called = {}

    def fake_import(kid, out_dir, query=""):
        called["kid"] = kid
        called["query"] = query
        (out_dir / "original.mp3").write_bytes(b"x" * 1000)
        return {
            "title": "NIGHT DANCER",
            "source": {"provider": "karaoke-mugen", "kid": kid},
        }

    monkeypatch.setattr(importer, "import_mugen_song", fake_import)
    skeleton = importer.import_song(
        query="NIGHT DANCER",
        out_dir=tmp_path,
        song_id="13393b41-9204-42ca-b014-e548bd60ca9f",
    )
    assert called == {
        "kid": "13393b41-9204-42ca-b014-e548bd60ca9f",
        "query": "NIGHT DANCER",
    }
    assert skeleton["source"]["provider"] == "karaoke-mugen"


def test_import_mugen_writes_lyrics_and_skips_whisper(tmp_path, monkeypatch):
    kid = "13393b41-9204-42ca-b014-e548bd60ca9f"
    monkeypatch.setattr(
        mugen,
        "fetch_kara",
        lambda value: {
            "kid": kid,
            "titles": {"eng": "NIGHT DANCER"},
            "titles_default_language": "eng",
            "singers": [{"name": "ReGLOSS"}],
            "langs": [{"name": "jpn"}],
            "lyrics_infos": [{"default": True, "filename": f"{kid}.ass"}],
            "mediafile": f"{kid}.mp4",
            "songname": "NIGHT DANCER",
        },
    )

    def fake_download(url, dest, timeout=600, min_size=200):
        dest = Path(dest)
        if dest.suffix == ".ass":
            dest.write_text(ASS, encoding="utf-8")
        else:
            dest.write_bytes(b"media" * 8000)

    monkeypatch.setattr(mugen, "download_file", fake_download)
    monkeypatch.setattr(
        mugen,
        "prepare_media",
        lambda src, out_dir: {
            "file": "original.mp3",
            "source": "mugen",
            "dual_audio": False,
            "needs_separate": True,
            "has_video": True,
        },
    )
    (tmp_path / "original.mp3").write_bytes(b"x" * 1000)
    (tmp_path / "mtv.mp4").write_bytes(b"v" * 1000)
    skeleton = mugen.import_mugen_song(kid, tmp_path, query="NIGHT DANCER")
    assert skeleton["needs_align"] is False
    assert skeleton["needs_separate"] is True
    assert skeleton.get("burned_lyrics") is not True
    assert skeleton["language"] == "ja"
    lyrics = (tmp_path / "lyrics.json").read_text(encoding="utf-8")
    assert "dou demo ii" in lyrics
    assert "karaoke-mugen" in lyrics
    assert "burned_lyrics" not in lyrics
    assert '"native_video": true' in lyrics


def test_process_import_keeps_mugen_lyrics(tmp_path, monkeypatch):
    song_id = "s1"
    out_dir = tmp_path / song_id
    out_dir.mkdir()
    (out_dir / "original.mp3").write_bytes(b"x" * 1000)
    (out_dir / "karaoke.m4a").write_bytes(b"k" * 1000)
    (out_dir / "mtv.mp4").write_bytes(b"v" * 1000)
    (out_dir / "lyrics.json").write_text(
        '{"language":"ja","alignment_source":"karaoke-mugen","cues":[{"text":"hello","start_ms":0,"end_ms":400,"tokens":[]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jobs,
        "import_song",
        lambda **kwargs: {
            "title": "NIGHT DANCER",
            "artist": "ReGLOSS",
            "language": "ja",
            "source": {"provider": "karaoke-mugen"},
            "audio": {"source": "mugen-dual", "dual_audio": True},
            "needs_separate": False,
            "needs_align": False,
            "has_video": True,
        },
    )
    separated = []
    aligned = []
    annotated = []
    monkeypatch.setattr(
        jobs, "separate_vocals", lambda *args, **kwargs: separated.append(True)
    )
    monkeypatch.setattr(
        jobs, "_align_and_mtv", lambda *args, **kwargs: aligned.append(True)
    )
    monkeypatch.setattr(
        jobs,
        "annotate_ja_lines",
        lambda *args, **kwargs: annotated.append(True) or {"lines": []},
    )
    monkeypatch.setattr(jobs, "apply_ja_annotation", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "write_subtitles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jobs,
        "get_song",
        lambda sid: {"title": "NIGHT DANCER", "artist": "ReGLOSS", "error": ""},
    )
    monkeypatch.setattr(
        jobs,
        "compose_mtv",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("should keep official MV")
        ),
    )
    jobs.process_import(
        song_id, "NIGHT DANCER", "13393b41-9204-42ca-b014-e548bd60ca9f", "ja"
    )
    assert separated == []
    assert aligned == []
    assert annotated == [True]


def test_process_import_separates_mugen_mp4(tmp_path, monkeypatch):
    song_id = "s1"
    out_dir = tmp_path / song_id
    out_dir.mkdir()
    (out_dir / "original.mp3").write_bytes(b"x" * 1000)
    (out_dir / "lyrics.json").write_text(
        '{"language":"en","alignment_source":"karaoke-mugen","cues":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jobs,
        "import_song",
        lambda **kwargs: {
            "title": "Give a reason",
            "artist": "Megumi Hayashibara",
            "language": "ja",
            "source": {
                "provider": "karaoke-mugen",
                "kid": "53dc255f-65fc-48cb-a2bb-ce58c2d08a3d",
                "songname": "JPN - Slayers Next - OP - Give a reason",
            },
            "audio": {"source": "mugen", "dual_audio": False},
            "needs_separate": True,
            "needs_align": False,
            "has_video": True,
        },
    )
    separated = []
    monkeypatch.setattr(
        jobs, "separate_vocals", lambda *args, **kwargs: separated.append(True)
    )
    monkeypatch.setattr(jobs, "_finish_ready_lyrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jobs, "get_song", lambda sid: {"title": "Give a reason", "error": ""}
    )
    jobs.process_import(
        song_id, "Give a reason", "53dc255f-65fc-48cb-a2bb-ce58c2d08a3d", "ja"
    )
    assert separated == [True]


def test_ensure_karaoke_stems_keeps_dual(tmp_path, monkeypatch):
    (tmp_path / "karaoke.m4a").write_bytes(b"k" * 100)
    (tmp_path / "original.mp3").write_bytes(b"o" * 100)
    monkeypatch.setattr(
        jobs,
        "separate_vocals",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dual")),
    )
    mode = jobs.ensure_karaoke_stems(
        tmp_path,
        tmp_path / "original.mp3",
        {
            "audio": {"source": "mugen-dual", "dual_audio": True},
            "source": {"provider": "karaoke-mugen"},
        },
    )
    assert mode == "dual"


def test_ensure_karaoke_stems_attaches_vocal_for_off_vocal(tmp_path, monkeypatch):
    src = tmp_path / "original.mp3"
    src.write_bytes(b"o" * 100)
    attached = []

    def fake_attach(out_dir, skeleton):
        attached.append(True)
        (out_dir / "original.mp3").write_bytes(b"v" * 200)
        return True

    monkeypatch.setattr(jobs, "attach_vocal_audio", fake_attach)
    monkeypatch.setattr(
        jobs,
        "_fallback_media",
        lambda src_path, out_dir: (out_dir / "karaoke.m4a").write_bytes(b"k" * 100),
    )
    monkeypatch.setattr(
        jobs,
        "separate_vocals",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("off-vocal+vocal")
        ),
    )
    mode = jobs.ensure_karaoke_stems(
        tmp_path,
        src,
        {
            "title": "群青 · YOASOBI",
            "source": {
                "provider": "karaoke-mugen",
                "songname": "JPN - YOASOBI - MV - Gunjô ~ Off Vocal Vers",
            },
            "audio": {"source": "mugen"},
        },
    )
    assert mode == "off-vocal+vocal"
    assert attached == [True]


def test_attach_vocal_audio_downloads_sibling(tmp_path, monkeypatch):
    skeleton = {
        "title": "群青",
        "source": {
            "provider": "karaoke-mugen",
            "kid": "off-kid",
            "query": "群青 YOASOBI",
            "songname": "Gunjô ~ Off Vocal Vers",
        },
        "audio": {},
    }
    monkeypatch.setattr(
        mugen,
        "search_mugen",
        lambda query, count=8, page=1: {
            "hits": [
                {"id": "off-kid", "off_vocal": True},
                {"id": "88bbec95-58e2-4407-adf2-74d7c6e4ac1d", "off_vocal": False},
            ]
        },
    )
    monkeypatch.setattr(
        mugen, "fetch_kara", lambda kid: {"kid": kid, "mediafile": f"{kid}.mp4"}
    )
    monkeypatch.setattr(
        mugen,
        "download_file",
        lambda url, dest, timeout=600, min_size=200: Path(dest).write_bytes(
            b"m" * 30000
        ),
    )
    extracted = []

    def fake_extract(src, dest, stream_index=None):
        extracted.append(dest.name)
        dest.write_bytes(b"a" * 100)

    monkeypatch.setattr(mugen, "extract_audio", fake_extract)
    assert mugen.attach_vocal_audio(tmp_path, skeleton) is True
    assert "original.mp3" in extracted
    assert skeleton["source"]["vocal_kid"] == "88bbec95-58e2-4407-adf2-74d7c6e4ac1d"


def test_attach_vocal_audio_retries_title_when_combined_query_has_no_hits(
    tmp_path, monkeypatch
):
    skeleton = {
        "title": "群青 · YOASOBI",
        "source": {
            "provider": "karaoke-mugen",
            "kid": "off-kid",
            "query": "群青 YOASOBI",
            "songname": "JPN - YOASOBI - MV - Gunjô ~ Off Vocal Vers",
        },
        "audio": {},
    }
    calls = []

    def fake_search(query, count=8, page=1):
        calls.append(query)
        if query == "群青 YOASOBI":
            return {"hits": []}
        return {
            "hits": [
                {"id": "other", "off_vocal": False, "songname": "JPN - Ado - MV - 群青"},
                {
                    "id": "vocal",
                    "off_vocal": False,
                    "songname": "JPN - YOASOBI - MV - Gunjô",
                },
            ]
        }

    monkeypatch.setattr(mugen, "search_mugen", fake_search)
    monkeypatch.setattr(mugen, "fetch_kara", lambda kid: {"mediafile": f"{kid}.mp4"})
    monkeypatch.setattr(
        mugen,
        "download_file",
        lambda url, dest, timeout=600, min_size=200: Path(dest).write_bytes(b"m" * 30000),
    )
    monkeypatch.setattr(
        mugen,
        "extract_audio",
        lambda src, dest, stream_index=None: Path(dest).write_bytes(b"v" * 100),
    )

    assert mugen.attach_vocal_audio(tmp_path, skeleton) is True
    assert calls == ["群青 YOASOBI", "群青"]
    assert skeleton["source"]["vocal_kid"] == "vocal"


def test_prepare_media_extracts_dual_tracks(tmp_path, monkeypatch):
    src = tmp_path / "song.mp4"
    src.write_bytes(b"x")
    mapped = []

    def fake_extract(src_path, dest, stream_index=None):
        mapped.append((dest.name, stream_index))
        dest.write_bytes(b"a" * 100)

    monkeypatch.setattr(
        mugen,
        "probe_streams",
        lambda path: [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio", "tags": {"title": "Karaoke"}},
            {"index": 2, "codec_type": "audio", "tags": {"title": "Guide vocals"}},
        ],
    )
    monkeypatch.setattr(mugen, "extract_audio", fake_extract)
    monkeypatch.setattr(
        mugen,
        "install_video",
        lambda src_path, dest: dest.write_bytes(b"v" * 2000) or True,
    )
    info = mugen.prepare_media(src, tmp_path)
    assert info["dual_audio"] is True
    assert info["needs_separate"] is False
    assert info["source"] == "mugen-dual"
    assert ("karaoke.m4a", 1) in mapped
    assert ("original.mp3", 2) in mapped
    assert (tmp_path / "mtv.mp4").exists()


def test_prepare_media_single_mix_still_needs_separation(tmp_path, monkeypatch):
    src = tmp_path / "song.mp4"
    src.write_bytes(b"x")
    mapped = []

    def fake_extract(src_path, dest, stream_index=None):
        mapped.append(dest.name)
        dest.write_bytes(b"a" * 100)

    monkeypatch.setattr(
        mugen,
        "probe_streams",
        lambda path: [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio", "channels": 2},
        ],
    )
    monkeypatch.setattr(mugen, "extract_audio", fake_extract)
    monkeypatch.setattr(
        mugen,
        "install_video",
        lambda src_path, dest: dest.write_bytes(b"v" * 2000) or True,
    )
    info = mugen.prepare_media(src, tmp_path)
    assert info["dual_audio"] is False
    assert info["needs_separate"] is True
    assert info["source"] == "mugen"
    assert mapped == ["original.mp3"]


def test_prepare_media_renames_mp3_to_canonical_original(tmp_path, monkeypatch):
    src = tmp_path / "mugen.mp3"
    payload = b"already-an-mp3" * 100
    src.write_bytes(payload)
    monkeypatch.setattr(mugen, "probe_streams", lambda path: [])

    info = mugen.prepare_media(src, tmp_path)

    assert info["file"] == "original.mp3"
    assert info["source"] == "mugen"
    assert info["needs_separate"] is True
    assert (tmp_path / "original.mp3").read_bytes() == payload
    assert not src.exists()


GUNJOU_KARA = {
    "medias": [
        {
            "default": True,
            "duration": 262,
            "filename": "gunjou.mp4",
            "lyrics": [{"default": True, "filename": "gunjou.ass"}],
        }
    ],
    "data": {
        "kid": "2e626891-5435-4333-b9bc-90e270f74e8f",
        "songname": "JPN - YOASOBI - MV - Gunjô",
        "titles": {"jpn": "群青", "eng": "Gunjou", "qro": "Gunjô"},
        "titles_default_language": "eng",
        "tags": {
            "langs": ["lang-jpn"],
            "singers": ["singer-yoasobi"],
            "series": [],
        },
    },
}
GUNJOU_TAGS = [
    {"tag": {"tid": "lang-jpn", "name": "jpn"}},
    {"tag": {"tid": "singer-yoasobi", "name": "YOASOBI", "i18n": {"jpn": "YOASOBI"}}},
]


def test_index_builds_from_zip(tmp_path):
    import json
    import zipfile

    from lovktv.catalog import mugen_index

    kara_zip = tmp_path / "karaokes.zip"
    tag_zip = tmp_path / "tags.zip"
    with zipfile.ZipFile(kara_zip, "w") as archive:
        archive.writestr("karaokes/gunjou.kara.json", json.dumps(GUNJOU_KARA))
    with zipfile.ZipFile(tag_zip, "w") as archive:
        for index, tag in enumerate(GUNJOU_TAGS):
            archive.writestr(f"tags/{index}.tag.json", json.dumps(tag))
    items = mugen_index.build_items_from_zip(kara_zip, tag_zip)
    assert items[0]["titles"]["jpn"] == "群青"
    assert items[0]["artists"] == ["YOASOBI"]


def test_index_builds_and_searches_japanese_title():
    from lovktv.catalog import mugen_index

    items = mugen_index.build_items_from_files([GUNJOU_KARA], GUNJOU_TAGS)
    assert items[0]["kid"] == "2e626891-5435-4333-b9bc-90e270f74e8f"
    assert items[0]["artists"] == ["YOASOBI"]
    assert items[0]["language"] == "ja"
    found = mugen_index.search_items(items, "群青", count=5)
    assert found["total"] == 1
    assert found["hits"][0]["kid"] == items[0]["kid"]
    by_artist = mugen_index.search_items(items, "YOASOBI", count=5)
    assert by_artist["total"] == 1
    by_romaji = mugen_index.search_items(items, "gunjo", count=5)
    assert by_romaji["total"] == 1
    miss = mugen_index.search_items(items, "晴天", count=5)
    assert miss["total"] == 0


def test_search_mugen_uses_local_index(monkeypatch):
    from lovktv.catalog import mugen_index

    items = mugen_index.build_items_from_files([GUNJOU_KARA], GUNJOU_TAGS)
    mugen_index.set_items_for_tests(items)
    try:
        monkeypatch.setattr(
            mugen,
            "_search_mugen_api",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("kara.moe must stay unused")
            ),
        )
        result = mugen.search_mugen("群青", count=10, page=1)
    finally:
        mugen_index.reset_for_tests()
    assert result["hits"][0]["source"] == "mugen"
    assert result["hits"][0]["title"] == "群青"
    assert result["hits"][0]["artist"] == "YOASOBI"
    assert result["hits"][0]["id"] == "2e626891-5435-4333-b9bc-90e270f74e8f"


def test_fetch_kara_uses_index_before_live_api(monkeypatch):
    from lovktv.catalog import mugen_index

    items = mugen_index.build_items_from_files([GUNJOU_KARA], GUNJOU_TAGS)
    mugen_index.set_items_for_tests(items)
    try:
        monkeypatch.setattr(
            mugen,
            "get_json",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("live kara.moe")
            ),
        )
        kara = mugen.fetch_kara("2e626891-5435-4333-b9bc-90e270f74e8f")
    finally:
        mugen_index.reset_for_tests()
    assert kara["kid"] == "2e626891-5435-4333-b9bc-90e270f74e8f"
    assert kara["mediafile"] == "gunjou.mp4"
    assert kara["lyrics_infos"][0]["filename"] == "gunjou.ass"


def test_complete_mugen_audio_keeps_lyrics_when_media_missing(tmp_path, monkeypatch):
    (tmp_path / "lyrics.json").write_text('{"cues":[]}', encoding="utf-8")
    skeleton = {
        "title": "群青 · YOASOBI",
        "artist": "YOASOBI",
        "source": {"provider": "karaoke-mugen", "kid": "kid"},
        "audio": {"file": "", "source": "mugen"},
        "needs_separate": True,
    }
    monkeypatch.setattr(
        importer,
        "pick_bilibili_mv",
        lambda title, artist="": {"bvid": "BV1xx", "title": "群青 MV"},
    )
    monkeypatch.setattr(
        importer,
        "try_bilibili_download",
        lambda bvid, mp3, video: mp3.write_bytes(b"a" * 2000) or True,
    )
    filled = importer._complete_mugen_audio(skeleton, tmp_path, "群青")
    assert filled["audio"]["source"] == "mugen-bilibili"
    assert (tmp_path / "original.mp3").exists()
    assert filled["source"]["provider"] == "karaoke-mugen"
