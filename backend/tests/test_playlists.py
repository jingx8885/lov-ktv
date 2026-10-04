"""Playlist storage + router behaviour on the sqlite test backend."""

import os
from pathlib import Path

import pytest
from starlette.requests import Request


def _req(headers=None):
    headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return store


def test_playlist_crud(db):
    from lovktv.storage import playlists as pl

    owner = "m:testmachine"
    assert pl.list_playlists(owner) == []
    one = pl.create_playlist(owner, "日语练习")
    two = pl.create_playlist(owner, "粤语老歌")
    assert one["id"].startswith("pl")
    names = [p["name"] for p in pl.list_playlists(owner)]
    # Newest first.
    assert names == ["粤语老歌", "日语练习"]
    song = db.create_song(" Lemon ", "米津玄師", "ja")
    assert pl.add_song(owner, one["id"], song["id"])
    # Duplicate add is an idempotent no-op.
    assert pl.add_song(owner, one["id"], song["id"])
    got = pl.get_playlist(owner, one["id"])
    assert got["count"] == 1
    assert pl.playlist_song_ids(one["id"]) == [song["id"]]
    marked = pl.list_playlists(owner, song_id=song["id"])
    assert [p["has_song"] for p in marked] == [False, True]
    assert pl.name_taken(owner, "日语练习")
    assert not pl.name_taken(owner, "日语练习", exclude_id=one["id"])
    assert pl.rename_playlist(owner, one["id"], "日语歌单")
    # Cross-owner writes are refused.
    assert not pl.rename_playlist("m:other", one["id"], "抢")
    assert not pl.remove_song("m:other", one["id"], song["id"])
    assert pl.remove_song(owner, one["id"], song["id"])
    assert not pl.remove_song(owner, one["id"], song["id"])
    assert pl.delete_playlist(owner, one["id"])
    assert pl.get_playlist(owner, one["id"]) is None
    assert pl.delete_playlist(owner, two["id"])
    assert pl.list_playlists(owner) == []


def test_playlist_items_follow_song_delete(db):
    from lovktv.storage import playlists as pl

    owner = "m:testmachine"
    song = db.create_song("红日", "李克勤", "yue")
    lst = pl.create_playlist(owner, "热歌")
    assert pl.add_song(owner, lst["id"], song["id"])
    assert db.delete_song(song["id"])
    assert pl.playlist_song_ids(lst["id"]) == []
    assert pl.get_playlist(owner, lst["id"])["count"] == 0


def test_merge_owners_moves_lists(db):
    from lovktv.storage import playlists as pl

    guest, account = "m:guest1", "u:u1"
    pl.create_playlist(account, "我的歌单")
    pl.create_playlist(guest, "我的歌单")
    guest_list = pl.list_playlists(guest)[0]
    song = db.create_song("歌", "人", "zh")
    pl.add_song(guest, guest_list["id"], song["id"])
    pl.merge_owners(guest, account)
    assert pl.list_playlists(guest) == []
    names = sorted(p["name"] for p in pl.list_playlists(account))
    assert names == ["我的歌单", "我的歌单 (2)"]
    moved = [p for p in pl.list_playlists(account) if p["count"] == 1][0]
    assert pl.playlist_song_ids(moved["id"]) == [song["id"]]
    # Re-running the merge is a no-op.
    pl.merge_owners(guest, account)
    assert len(pl.list_playlists(account)) == 2


def test_router_endpoints(db):
    from lovktv.routers import playlists as api

    req = _req({"x-lovktv-machine": "machinetest01"})
    assert api.api_playlists(req)["playlists"] == []
    bad = api.api_playlists(_req({}))
    assert bad["playlists"] == []
    try:
        api.api_create_playlist(req, {"name": "  "})
        pytest.fail("empty name accepted")
    except Exception as exc:
        assert getattr(exc, "status_code", 400) == 400
    created = api.api_create_playlist(req, {"name": "开车听"})
    pid = created["playlist"]["id"]
    try:
        api.api_create_playlist(req, {"name": "开车听"})
        pytest.fail("duplicate name accepted")
    except Exception as exc:
        assert getattr(exc, "status_code", 0) == 409
    song = db.create_song("晴天", "周杰伦", "zh")
    db.update_song(song["id"], status="ready")
    added = api.api_playlist_add(req, pid, {"song_id": song["id"]})
    assert added["playlist"]["count"] == 1
    detail = api.api_playlist_songs(req, pid)
    assert [s["id"] for s in detail["songs"]] == [song["id"]]
    assert detail["songs"][0]["favorite"] is False
    renamed = api.api_rename_playlist(req, pid, {"name": "循环"})
    assert renamed["playlist"]["name"] == "循环"
    removed = api.api_playlist_remove(req, pid, song["id"])
    assert removed["playlist"]["count"] == 0
    assert api.api_delete_playlist(req, pid)["ok"]
    try:
        api.api_playlist_songs(req, pid)
        pytest.fail("deleted playlist still readable")
    except Exception as exc:
        assert getattr(exc, "status_code", 0) == 404
    # A different owner sees an empty world.
    other = api.api_playlists(_req({"x-lovktv-machine": "machineother9"}))
    assert other["playlists"] == []
