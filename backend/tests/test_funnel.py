import json

from fastapi.testclient import TestClient


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "funnel.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return store


def test_funnel_events_store_and_summary(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    store.track_funnel_event("landing_view", "g:abc", '{"utm_source":"hn"}')
    store.track_funnel_event("song_queued", "u:1", '{"src":"search"}')
    store.track_funnel_event("paid", "u:1", '{"plan":"pro"}')
    summary = store.funnel_summary(30)
    assert summary["by_kind"]["landing_view"] == 1
    assert summary["by_kind"]["song_queued"] == 1
    assert summary["by_kind"]["paid"] == 1
    today = max(summary["daily"])
    assert summary["daily"][today]["landing_view"] == 1


def test_funnel_beacon_is_allowlisted(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    from lovktv.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/funnel",
            json={"kind": "landing_view", "meta": {"utm_source": "hn", "evil": "x"}},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # 白名单外的事件类型直接拒绝，不写入
        resp = client.post("/api/funnel", json={"kind": "paid"})
        assert resp.json()["ok"] is False
        # 白名单外的 meta 键被剥掉
        summary = store.funnel_summary(30)
        assert summary["by_kind"].get("landing_view") == 1
        assert "paid" not in summary["by_kind"]
