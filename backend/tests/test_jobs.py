import json
import threading

from lovktv.workers import jobs


def test_resume_stuck_jobs_includes_queued_and_aligning(monkeypatch, tmp_path):
    spawned: list[tuple[str, tuple]] = []
    (tmp_path / "a1").mkdir()
    (tmp_path / "a1" / "original.mp3").write_bytes(b"x")
    monkeypatch.setattr(
        jobs,
        "list_songs",
        lambda: [
            {
                "id": "q1",
                "status": "queued",
                "title": "Get along",
                "artist": "林原めぐみ",
                "netease_id": "22689487",
                "language": "ja",
            },
            {
                "id": "a1",
                "status": "aligning",
                "title": "Give a reason",
                "language": "ja",
            },
            {
                "id": "f1",
                "status": "fetching",
                "title": "A million dreams",
                "artist": "Hugh Jackman",
                "netease_id": "1",
                "language": "en",
            },
            {"id": "r1", "status": "ready", "title": "群青"},
        ],
    )
    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(
        jobs, "spawn", lambda fn, *args, **kwargs: spawned.append((fn.__name__, args))
    )
    assert jobs.resume_stuck_jobs() == 3
    assert spawned[0][0] == "process_realign"
    assert spawned[0][1][0] == "a1"
    assert spawned[0][1][2] is True
    assert spawned[1][0] == "process_import"
    assert spawned[1][1][0] == "f1"
    assert spawned[2][0] == "process_import"
    assert spawned[2][1][0] == "q1"


def test_job_queue_deduplicates_only_while_pending():
    queue = jobs.JobQueue(worker_name="test-lovktv-jobs")
    started = threading.Event()
    release = threading.Event()

    def work(song_id):
        assert song_id == "s1"
        started.set()
        release.wait(1)

    assert queue.submit(work, "s1") is True
    assert started.wait(1)
    assert queue.submit(work, "s1") is False
    release.set()
    queue._jobs.join()
    assert queue.submit(work, "s1") is True
    queue._jobs.join()


def test_song_repository_is_replaceable(monkeypatch):
    class FakeSongs:
        def get(self, song_id):
            return {"id": song_id, "status": "ready"}

        def list(self):
            return [{"id": "s1"}]

        def update(self, song_id, **fields):
            return None

        def retry_query(self, song):
            return "fake query"

    monkeypatch.setattr(jobs, "song_repository", FakeSongs())
    assert jobs.get_song("s1")["status"] == "ready"
    assert jobs.list_songs() == [{"id": "s1"}]
    assert jobs.retry_query({}) == "fake query"


def test_job_recovery_accepts_repository_and_submitter(tmp_path):
    queued = []

    class FakeSongs:
        def list(self):
            return [{"id": "q1", "status": "queued", "title": "测试", "language": "zh"}]

        def retry_query(self, song):
            return song["title"]

    recovery = jobs.JobRecovery(
        repository=FakeSongs(),
        submit=lambda fn, *args: queued.append((fn.__name__, args)),
        media_dir=tmp_path,
    )
    assert recovery.resume() == 1
    assert queued == [("process_import", ("q1", "测试", "", "zh"))]


def test_finish_ready_lyrics_forces_romaji_restore(tmp_path, monkeypatch):
    out_dir = tmp_path / "s1"
    out_dir.mkdir()
    (out_dir / "lyrics.json").write_text(
        '{"language":"en","alignment_source":"karaoke-mugen","cues":['
        '{"text":"moshimo negai hitotsu dake","start_ms":0,"end_ms":800,"tokens":[]}]}',
        encoding="utf-8",
    )
    seen: dict = {}

    def fake_ann(lines, **kwargs):
        seen["lines"] = lines
        seen.update(kwargs)
        return {"lines": [], "model": "test"}

    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jobs,
        "get_song",
        lambda sid: {"title": "Beautiful World", "artist": "Utada", "language": "ja"},
    )
    monkeypatch.setattr(jobs, "annotate_ja_lines", fake_ann)
    monkeypatch.setattr(jobs, "apply_ja_annotation", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "translate_lines", lambda *args, **kwargs: {"lines": []})
    monkeypatch.setattr(jobs, "apply_zh_translation", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "write_subtitles", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "compose_mtv", lambda *args, **kwargs: None)
    jobs._finish_ready_lyrics(
        "s1", out_dir, out_dir / "lyrics.json", "ja", rebuild_mtv=True
    )
    assert seen.get("force") is True
    assert seen.get("lines") == ["moshimo negai hitotsu dake"]


def test_finish_ready_lyrics_translates_english(tmp_path, monkeypatch):
    out_dir = tmp_path / "s2"
    out_dir.mkdir()
    (out_dir / "lyrics.json").write_text(
        '{"language":"en","cues":[{"text":"in the end","start_ms":0,"end_ms":800,"tokens":[]}]}',
        encoding="utf-8",
    )
    called = {}

    def fake_tr(lines, **kwargs):
        called["lines"] = lines
        return {"lines": [{"source": "in the end", "zh": "到最后", "units": []}]}

    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jobs, "get_song", lambda sid: {"title": "In The End", "artist": "LP"}
    )
    monkeypatch.setattr(jobs, "translate_lines", fake_tr)
    monkeypatch.setattr(jobs, "write_subtitles", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "compose_mtv", lambda *args, **kwargs: None)
    jobs._finish_ready_lyrics(
        "s2", out_dir, out_dir / "lyrics.json", "en", rebuild_mtv=True
    )
    assert called.get("lines") == ["in the end"]


def test_has_native_mtv_from_bilibili_skeleton(tmp_path):
    (tmp_path / "skeleton.json").write_text('{"has_video": true}', encoding="utf-8")
    (tmp_path / "mtv.mp4").write_bytes(b"v")
    assert jobs._has_native_mtv(tmp_path) is True
    assert jobs._has_native_mtv(tmp_path / "missing") is False


def test_native_timed_requires_close_media_duration(tmp_path, monkeypatch):
    out = tmp_path / "s"
    out.mkdir()
    (out / "mtv.mp4").write_bytes(b"v")
    (out / "lyrics.json").write_text(
        '{"cues":[{"start_ms":1000,"end_ms":118000}]}', encoding="utf-8"
    )
    skeleton = {"has_video": True, "source": {"provider": "karaoke-mugen"}}
    monkeypatch.setattr(jobs, "probe_duration_ms", lambda path: 120000)
    assert jobs._native_timed_matches_media(out, skeleton, out / "original.mp3")
    monkeypatch.setattr(jobs, "probe_duration_ms", lambda path: 180000)
    assert not jobs._native_timed_matches_media(out, skeleton, out / "original.mp3")


def test_realign_keeps_karaoke_mugen_timeline(tmp_path, monkeypatch):
    out = tmp_path / "m1"
    out.mkdir()
    (out / "original.mp3").write_bytes(b"audio")
    (out / "lyrics.json").write_text(
        '{"alignment_source":"karaoke-mugen","cues":[{"text":"hello","start_ms":100,"end_ms":500}]}',
        encoding="utf-8",
    )
    (out / "skeleton.json").write_text(
        '{"source":{"provider":"karaoke-mugen"},"audio":{"source":"mugen"}}',
        encoding="utf-8",
    )
    called = []
    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jobs,
        "_finish_ready_lyrics",
        lambda *args, **kwargs: called.append((args, kwargs)),
    )
    monkeypatch.setattr(
        jobs,
        "_align_and_mtv",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must keep Mugen timing")),
    )
    jobs.process_realign("m1", "ja", force=True)
    assert called and called[0][0][0:2] == ("m1", out)


def test_refresh_mugen_off_vocal_restores_sibling_vocal_without_overwriting_karaoke(
    tmp_path, monkeypatch
):
    out = tmp_path / "m1"
    out.mkdir()
    (out / "original.mp3").write_bytes(b"old-off-vocal")
    (out / "karaoke.m4a").write_bytes(b"official-karaoke")
    (out / "mtv.mp4").write_bytes(b"off-vocal-mv")
    skeleton = {
        "title": "群青 · YOASOBI",
        "source": {
            "provider": "karaoke-mugen",
            "songname": "JPN - YOASOBI - MV - Gunjô ~ Off Vocal Vers",
            "vocal_kid": "vocal-kid",
        },
        "audio": {"source": "mugen", "has_original_vocal": True},
    }
    (out / "skeleton.json").write_text(json.dumps(skeleton), encoding="utf-8")
    extracted = []

    def restore_vocal(folder, value):
        extracted.append(True)
        (folder / "original.mp3").write_bytes(b"real-vocal")
        return True

    monkeypatch.setattr(jobs, "attach_vocal_audio", restore_vocal)
    monkeypatch.setattr(
        jobs,
        "extract_mv_mp3",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must not extract off-vocal MV into original")
        ),
    )
    monkeypatch.setattr(
        jobs,
        "separate_vocals",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must keep the official karaoke stem")
        ),
    )

    result = jobs._refresh_audio_tracks(out, skeleton)
    assert extracted == [True]
    assert result.read_bytes() == b"real-vocal"
    assert (out / "karaoke.m4a").read_bytes() == b"official-karaoke"


def test_restore_mugen_timeline_uses_untouched_ass(tmp_path, monkeypatch):
    out = tmp_path / "m1"
    out.mkdir()
    (out / "mugen.ass").write_text("original ass", encoding="utf-8")
    seen = {}

    def fake_timeline(raw, language):
        seen["args"] = (raw, language)
        return {
            "language": language,
            "alignment_source": "karaoke-mugen",
            "cues": [{"text": "hello", "start_ms": 100, "end_ms": 500, "tokens": []}],
        }

    monkeypatch.setattr("lovktv.catalog.mugen.timeline_from_ass", fake_timeline)
    monkeypatch.setattr(jobs, "write_subtitles", lambda timeline, out_dir: seen.update(timeline))
    monkeypatch.setattr(jobs, "_has_native_mtv", lambda out_dir: True)
    assert jobs._restore_mugen_timeline(out, "en") is True
    assert seen["args"] == ("original ass", "en")
    assert seen["alignment_source"] == "karaoke-mugen"
    assert seen["native_video"] is True


def test_resume_stuck_align_keeps_bilibili_mv(monkeypatch, tmp_path):
    out = tmp_path / "b1"
    out.mkdir()
    (out / "original.mp3").write_bytes(b"x")
    (out / "mtv.mp4").write_bytes(b"v")
    (out / "skeleton.json").write_text('{"has_video": true}', encoding="utf-8")
    spawned: list[tuple] = []
    monkeypatch.setattr(
        jobs,
        "list_songs",
        lambda: [{"id": "b1", "status": "aligning", "language": "zh"}],
    )
    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(
        jobs, "spawn", lambda fn, *args, **kwargs: spawned.append((fn.__name__, args))
    )
    assert jobs.resume_stuck_jobs() == 1
    assert spawned[0] == ("process_realign", ("b1", "zh", False))


def test_forced_realign_reimports_when_local_media_is_missing(monkeypatch, tmp_path):
    song = {
        "id": "m1",
        "title": "Get along · 林原めぐみ",
        "artist": "林原めぐみ",
        "language": "ja",
        "netease_id": "22689487",
    }
    calls = []
    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "get_song", lambda song_id: song)
    monkeypatch.setattr(
        jobs,
        "process_import",
        lambda *args: calls.append(args),
    )

    jobs.process_realign("m1", "ja", force=True)

    assert calls == [("m1", "Get along 林原めぐみ", "22689487", "ja")]


def test_finish_ready_lyrics_keeps_bilibili_mv_even_when_rebuild(tmp_path, monkeypatch):
    out_dir = tmp_path / "s1"
    out_dir.mkdir()
    (out_dir / "mtv.mp4").write_bytes(b"v" * 2000)
    (out_dir / "skeleton.json").write_text('{"has_video": true}', encoding="utf-8")
    (out_dir / "lyrics.json").write_text(
        '{"language":"zh","alignment_source":"official","cues":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(jobs, "update_song", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "get_song", lambda sid: {"title": "晴天", "artist": ""})
    monkeypatch.setattr(
        jobs,
        "compose_mtv",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("keep bili mv")),
    )
    jobs._finish_ready_lyrics(
        "s1", out_dir, out_dir / "mtv.mp4", "zh", rebuild_mtv=True
    )
    timeline = __import__("json").loads(
        (out_dir / "lyrics.json").read_text(encoding="utf-8")
    )
    assert timeline["native_video"] is True


def test_realign_preserves_native_mv_and_translation_annotations():
    previous = {
        "native_video": True,
        "translation": "lovjpn-zh",
        "translation_model": "test-model",
        "cues": [
            {
                "text": "I stay",
                "zh": "我留下",
                "tokens": [
                    {"text": "I", "zh": "我"},
                    {"text": "stay", "zh": "留下"},
                ],
            }
        ],
    }
    timeline = {
        "language": "en",
        "cues": [
            {
                "text": "I stay",
                "tokens": [
                    {"text": "I"},
                    {"text": "stay"},
                ],
            }
        ],
    }

    jobs._preserve_timeline_annotations(previous, timeline)

    assert timeline["native_video"] is True
    assert timeline["translation"] == "lovjpn-zh"
    assert timeline["cues"][0]["zh"] == "我留下"
    assert [token["zh"] for token in timeline["cues"][0]["tokens"]] == ["我", "留下"]
