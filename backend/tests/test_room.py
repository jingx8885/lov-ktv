import pytest
from lovktv.store import enqueue, ensure_room, play_now, skip


def _ready(store, song_id: str) -> None:
    store.update_song(song_id, status="ready")


def test_skip_removes_current_and_plays_next(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    store.create_song("A", "a", "zh")
    a = store.list_songs()[0]["id"]
    store.create_song("B", "b", "zh")
    b = [s["id"] for s in store.list_songs() if s["title"] == "B"][0]
    store.create_song("C", "c", "zh")
    c = [s["id"] for s in store.list_songs() if s["title"] == "C"][0]
    for song_id in (a, b, c):
        _ready(store, song_id)
    ensure_room("SKIP1")
    enqueue("SKIP1", a)
    enqueue("SKIP1", a)
    enqueue("SKIP1", b)
    enqueue("SKIP1", c)
    assert [item["song_id"] for item in store.room_snapshot("SKIP1")["queue"]] == [a, b, c]
    play_now("SKIP1", song_id=a)
    snap = skip("SKIP1")
    assert [item["song_id"] for item in snap["queue"]] == [b, c]
    assert snap["now_playing"]["song_id"] == b
    snap = skip("SKIP1")
    assert [item["song_id"] for item in snap["queue"]] == [c]
    assert snap["now_playing"]["song_id"] == c
    snap = skip("SKIP1")
    assert snap["queue"] == []
    assert snap["now_playing"] is None


def test_enqueue_rejects_songs_that_are_not_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    song = store.create_song("失败的歌", "x", "zh")
    store.update_song(song["id"], status="failed", error="音频下载失败")
    ensure_room("READY1")
    with pytest.raises(ValueError, match="还没就绪"):
        enqueue("READY1", song["id"])


def test_delete_failed_song_removes_files_and_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    ready = store.create_song("能唱", "a", "zh")
    failed = store.create_song("失败", "b", "zh")
    store.update_song(ready["id"], status="ready")
    store.update_song(failed["id"], status="failed", error="下载失败")
    (store.MEDIA_DIR / failed["id"] / "broken.txt").write_text("x", encoding="utf-8")
    ensure_room("DEL1")
    enqueue("DEL1", ready["id"])
    assert store.delete_song(failed["id"]) is True
    assert store.get_song(failed["id"]) is None
    assert not (store.MEDIA_DIR / failed["id"]).exists()
    assert [item["song_id"] for item in store.room_snapshot("DEL1")["queue"]] == [ready["id"]]


def test_catalog_enqueue_does_not_cut_in(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    first = store.create_song("正在唱", "a", "zh")
    extra = store.create_song("后来点的", "b", "zh")
    store.update_song(first["id"], status="ready")
    store.update_song(extra["id"], status="ready")
    ensure_room("Q1")
    waiting = enqueue("Q1", first["id"])
    assert waiting["now_playing"]["song_id"] == first["id"]
    assert [item["song_id"] for item in waiting["queue"]] == [first["id"]]
    started = play_now("Q1", item_id=waiting["queue"][0]["id"])
    assert started["now_playing"]["song_id"] == first["id"]
    queued = enqueue("Q1", extra["id"])
    assert queued["now_playing"]["song_id"] == first["id"]
    assert [item["song_id"] for item in queued["queue"]] == [first["id"], extra["id"]]
    jumped = play_now("Q1", song_id=extra["id"])
    assert jumped["now_playing"]["song_id"] == first["id"]


def test_enqueue_after_empty_queue_starts_song(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    first = store.create_song("第一首", "a", "zh")
    extra = store.create_song("再点一首", "b", "zh")
    store.update_song(first["id"], status="ready")
    store.update_song(extra["id"], status="ready")
    ensure_room("EMPTY1")
    started = enqueue("EMPTY1", first["id"])
    assert started["now_index"] == 0
    assert started["now_playing"]["song_id"] == first["id"]
    skip("EMPTY1")
    idle = store.room_snapshot("EMPTY1")
    assert idle["queue"] == []
    assert idle["now_playing"] is None
    again = enqueue("EMPTY1", extra["id"])
    assert again["now_playing"]["song_id"] == extra["id"]


def test_stuck_negative_index_heals_when_queue_has_songs(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import store
    import sqlite3

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    song = store.create_song("卡住的歌", "a", "zh")
    store.update_song(song["id"], status="ready")
    ensure_room("STUCK1")
    enqueue("STUCK1", song["id"])
    with sqlite3.connect(store.DB_PATH) as conn:
        conn.execute("UPDATE rooms SET now_index=-1 WHERE code=?", ("STUCK1",))
    snap = store.room_snapshot("STUCK1")
    assert snap["now_index"] == 0
    assert snap["now_playing"]["song_id"] == song["id"]


def test_retry_query_uses_title_and_artist():
    from lovktv.store import retry_query

    assert retry_query({"title": "Give a reason · 林原めぐみ", "artist": "林原めぐみ"}) == "Give a reason 林原めぐみ"
