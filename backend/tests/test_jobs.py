import threading

from lovktv import jobs


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
            {"id": "a1", "status": "aligning", "title": "Give a reason", "language": "ja"},
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
    monkeypatch.setattr(jobs, "spawn", lambda fn, *args, **kwargs: spawned.append((fn.__name__, args)))
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
    monkeypatch.setattr(jobs, "get_song", lambda sid: {"title": "Beautiful World", "artist": "Utada", "language": "ja"})
    monkeypatch.setattr(jobs, "annotate_ja_lines", fake_ann)
    monkeypatch.setattr(jobs, "apply_ja_annotation", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "translate_lines", lambda *args, **kwargs: {"lines": []})
    monkeypatch.setattr(jobs, "apply_zh_translation", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "write_subtitles", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "compose_mtv", lambda *args, **kwargs: None)
    jobs._finish_ready_lyrics("s1", out_dir, out_dir / "lyrics.json", "ja", rebuild_mtv=True)
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
    monkeypatch.setattr(jobs, "get_song", lambda sid: {"title": "In The End", "artist": "LP"})
    monkeypatch.setattr(jobs, "translate_lines", fake_tr)
    monkeypatch.setattr(jobs, "write_subtitles", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "compose_mtv", lambda *args, **kwargs: None)
    jobs._finish_ready_lyrics("s2", out_dir, out_dir / "lyrics.json", "en", rebuild_mtv=True)
    assert called.get("lines") == ["in the end"]


def test_has_native_mtv_from_bilibili_skeleton(tmp_path):
    (tmp_path / "skeleton.json").write_text('{"has_video": true}', encoding="utf-8")
    (tmp_path / "mtv.mp4").write_bytes(b"v")
    assert jobs._has_native_mtv(tmp_path) is True
    assert jobs._has_native_mtv(tmp_path / "missing") is False


def test_resume_stuck_align_keeps_bilibili_mv(monkeypatch, tmp_path):
    out = tmp_path / "b1"
    out.mkdir()
    (out / "original.mp3").write_bytes(b"x")
    (out / "mtv.mp4").write_bytes(b"v")
    (out / "skeleton.json").write_text('{"has_video": true}', encoding="utf-8")
    spawned: list[tuple] = []
    monkeypatch.setattr(jobs, "list_songs", lambda: [{"id": "b1", "status": "aligning", "language": "zh"}])
    monkeypatch.setattr(jobs, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "spawn", lambda fn, *args, **kwargs: spawned.append((fn.__name__, args)))
    assert jobs.resume_stuck_jobs() == 1
    assert spawned[0] == ("process_realign", ("b1", "zh", False))


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
    jobs._finish_ready_lyrics("s1", out_dir, out_dir / "mtv.mp4", "zh", rebuild_mtv=True)
    timeline = __import__("json").loads((out_dir / "lyrics.json").read_text(encoding="utf-8"))
    assert timeline["native_video"] is True
