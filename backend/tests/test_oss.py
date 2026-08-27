from fastapi.testclient import TestClient


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.delenv("ALIYUN_OSS_ENABLED", raising=False)
    monkeypatch.delenv("ALIYUN_OSS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ALIYUN_OSS_ACCESS_KEY_SECRET", raising=False)
    from lovktv import config, main, store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    config.DATA_DIR = tmp_path
    config.MEDIA_DIR = tmp_path / "media"
    config.ALIYUN_OSS_ENABLED = False
    return main


def test_media_falls_back_to_local(tmp_path, monkeypatch):
    main = _boot(tmp_path, monkeypatch)
    folder = tmp_path / "media" / "abc123"
    folder.mkdir(parents=True)
    (folder / "karaoke.m4a").write_bytes(b"audio")
    with TestClient(main.app) as client:
        res = client.get("/media/abc123/karaoke.m4a")
    assert res.status_code == 200
    assert res.content == b"audio"


def test_media_redirects_to_oss_when_local_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.setenv("ALIYUN_OSS_ENABLED", "true")
    monkeypatch.setenv("ALIYUN_OSS_ACCESS_KEY_ID", "idididididididididididi")
    monkeypatch.setenv("ALIYUN_OSS_ACCESS_KEY_SECRET", "secret")
    monkeypatch.setenv("ALIYUN_OSS_ENDPOINT", "oss-cn-shenzhen.aliyuncs.com")
    monkeypatch.setenv("ALIYUN_OSS_BUCKET_NAME", "lovbrowser")
    monkeypatch.setenv("LOVKTV_OSS_PREFIX", "lovktv")
    monkeypatch.setenv("ALIYUN_OSS_DOWNLOAD_DOMAIN", "https://lovbrowser.oss-cn-shenzhen.aliyuncs.com")
    from importlib import reload
    from lovktv import config, oss, main, store

    reload(config)
    reload(oss)
    reload(main)
    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    (tmp_path / "media").mkdir(parents=True, exist_ok=True)
    with TestClient(main.app) as client:
        res = client.get("/media/abc123/mtv.mp4", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "https://lovbrowser.oss-cn-shenzhen.aliyuncs.com/lovktv/abc123/mtv.mp4"


def test_publish_files_includes_every_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from importlib import reload
    from lovktv import config, oss

    reload(config)
    reload(oss)
    folder = tmp_path / "song"
    folder.mkdir()
    (folder / "karaoke.m4a").write_bytes(b"a")
    (folder / "asr.json").write_text("{}", encoding="utf-8")
    (folder / "visual_config.json").write_text("{}", encoding="utf-8")
    (folder / "timeline.json").write_text("{}", encoding="utf-8")
    names = {p.name for p in oss.publish_files(folder)}
    assert names == {"karaoke.m4a", "asr.json", "visual_config.json", "timeline.json"}


def test_cors_allows_media_from_star_or_ktv():
    from lovktv.oss import MEDIA_CORS_XML, cors_allows_media, merge_cors_xml

    assert cors_allows_media(MEDIA_CORS_XML)
    assert cors_allows_media(
        "<CORSConfiguration><CORSRule>"
        "<AllowedOrigin>https://ktv.lovbrowser.com</AllowedOrigin>"
        "<AllowedMethod>GET</AllowedMethod>"
        "</CORSRule></CORSConfiguration>"
    )
    assert not cors_allows_media(
        "<CORSConfiguration><CORSRule>"
        "<AllowedOrigin>https://stock.lovbrowser.com</AllowedOrigin>"
        "<AllowedMethod>GET</AllowedMethod>"
        "</CORSRule></CORSConfiguration>"
    )
    merged = merge_cors_xml(
        "<CORSConfiguration><CORSRule>"
        "<AllowedOrigin>https://stock.lovbrowser.com</AllowedOrigin>"
        "<AllowedMethod>PUT</AllowedMethod>"
        "</CORSRule></CORSConfiguration>"
    )
    assert cors_allows_media(merged)
    assert "stock.lovbrowser.com" in merged
    assert merge_cors_xml(MEDIA_CORS_XML) == MEDIA_CORS_XML


def test_publish_noop_without_oss(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.delenv("ALIYUN_OSS_ENABLED", raising=False)
    from importlib import reload
    from lovktv import config, oss

    reload(config)
    reload(oss)
    assert oss.publish_song("missing") == []
    assert oss.oss_ready() is False
