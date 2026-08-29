from fastapi.testclient import TestClient


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.delenv("LOVKTV_PUBLIC_URL", raising=False)
    from lovktv import main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    monkeypatch.setattr("lovktv.catalog.mugen_index.prefetch_index", lambda: None)
    return main


def test_lifespan_health_and_public_acceptance_paths(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch)
    with TestClient(main.app, base_url="http://127.0.0.1:8787") as client:
        health = client.get("/healthz")
        host = client.get("/api/host")
        pages = [client.get(path) for path in ("/", "/tv.html", "/m.html")]
        assert health.status_code == 200
        assert health.json()["ready"] is True
        assert health.json()["worker"]["running"] is True
        assert host.status_code == 200
        assert host.json()["worker"]["running"] is True
        assert all(page.status_code == 200 for page in pages)
    assert main.job_queue.health()["running"] is False


def test_job_queue_start_stop_drops_pending_jobs():
    from lovktv.jobs import JobQueue

    queue = JobQueue(worker_name="test-lifecycle")
    started = __import__("threading").Event()
    release = __import__("threading").Event()

    def work(_song_id):
        started.set()
        release.wait(2)

    assert queue.start() is True
    assert queue.submit(work, "running") is True
    assert started.wait(1)
    assert queue.submit(work, "pending") is True
    release.set()
    assert queue.stop(timeout=2) is True
    assert queue.health() == {"running": False, "queued": 0, "pending": 0}
