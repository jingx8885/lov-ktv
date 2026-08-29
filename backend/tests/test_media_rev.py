import json
from pathlib import Path

from fastapi.testclient import TestClient

from lovktv.store import media_flags, media_rev, with_media_flags


def test_media_rev_changes_when_file_bytes_or_mtime_change(tmp_path, monkeypatch):
    monkeypatch.setattr("lovktv.store.MEDIA_DIR", tmp_path)
    folder = tmp_path / "s1"
    folder.mkdir()
    karaoke = folder / "karaoke.m4a"
    karaoke.write_bytes(b"old")
    first = media_rev("s1")
    assert first
    karaoke.write_bytes(b"new-audio")
    second = media_rev("s1")
    assert second
    assert first != second
    flags = media_flags("s1")
    assert flags["media_rev"] == second
    song = with_media_flags({"id": "s1", "title": "夜曲"})
    assert song["media_rev"] == second


def test_media_rev_falls_back_to_oss_marker(tmp_path, monkeypatch):
    monkeypatch.setattr("lovktv.store.MEDIA_DIR", tmp_path)
    folder = tmp_path / "s2"
    folder.mkdir()
    (folder / "oss.json").write_text(
        '{"files":["karaoke.m4a"],"media_rev":"fromoss12"}', encoding="utf-8"
    )
    assert media_rev("s2") == "fromoss12"


def test_write_marker_records_media_rev(tmp_path, monkeypatch):
    monkeypatch.setattr("lovktv.store.MEDIA_DIR", tmp_path)
    monkeypatch.setattr("lovktv.oss.MEDIA_DIR", tmp_path)
    folder = tmp_path / "s3"
    folder.mkdir()
    (folder / "karaoke.m4a").write_bytes(b"audio")
    from lovktv.oss import write_marker
    from lovktv.store import media_rev

    marker = write_marker("s3", ["karaoke.m4a"])
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["media_rev"] == media_rev("s3")
    assert payload["files"] == ["karaoke.m4a"]


def test_song_and_media_urls_use_media_rev(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import config, main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    config.MEDIA_DIR = tmp_path / "media"
    main.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    song = store.create_song("夜曲", "周杰伦")
    folder = Path(store.MEDIA_DIR) / song["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "karaoke.m4a").write_bytes(b"audio")
    (folder / "lyrics.json").write_text('{"cues":[]}', encoding="utf-8")
    store.update_song(song["id"], status="ready")
    rev = store.media_rev(song["id"])
    with TestClient(main.app) as client:
        detail = client.get(f"/api/songs/{song['id']}").json()
        page = client.get("/m.html")
        mix = client.get("/tv/playback/js/media/mix.js")
        media = client.get(f"/media/{song['id']}/karaoke.m4a?v={rev}")
    assert detail["media_rev"] == rev
    assert "mediaRevFor" in mix.text
    assert "ja-kanji" not in mix.text
    assert "stem2" not in mix.text
    assert media.status_code == 200
    assert media.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert 'src="/phone/app.js?v=' in page.text
