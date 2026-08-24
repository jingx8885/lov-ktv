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
    assert spawned[1][0] == "process_import"
    assert spawned[1][1][0] == "f1"
    assert spawned[2][0] == "process_import"
    assert spawned[2][1][0] == "q1"
