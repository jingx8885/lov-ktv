from lovktv.catalog import fetch
from lovktv.catalog import http as catalog_http


def _no_bilibili(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve_bilibili_source", lambda *args, **kwargs: {})


def test_curl_and_ytdlp_omit_proxy_by_default(monkeypatch):
    monkeypatch.delenv("LOVKTV_HTTPS_PROXY", raising=False)
    assert catalog_http.curl_proxy_args() == []
    assert catalog_http.ytdlp_proxy_args() == []


def test_curl_and_ytdlp_use_lovktv_https_proxy(monkeypatch):
    monkeypatch.setenv("LOVKTV_HTTPS_PROXY", "http://lov-stock-clash:7890")
    assert catalog_http.curl_proxy_args() == ["-x", "http://lov-stock-clash:7890"]
    assert catalog_http.ytdlp_proxy_args() == ["--proxy", "http://lov-stock-clash:7890"]


def test_resolve_prefers_playable_soundcloud(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    _no_bilibili(monkeypatch)
    monkeypatch.setattr(fetch, "probe_netease_url", lambda song_id: False)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/usr/bin/yt-dlp")

    def fake_list(query, ytdlp, provider, count=15):
        if provider == "youtube":
            return [
                {
                    "url": "https://youtube.com/watch?v=dead",
                    "title": "Give a reason",
                    "duration": 100,
                }
            ]
        return [
            {
                "url": "https://soundcloud.com/right-track",
                "title": "Give a reason",
                "duration": 100,
            }
        ]

    monkeypatch.setattr(fetch, "_list_ytdlp", fake_list)
    monkeypatch.setattr(
        fetch,
        "_ytdlp_direct_url",
        lambda page: "" if "youtube" in page else f"{page}/direct",
    )
    source = fetch.resolve_audio_source("22689669", "Give a reason", "林原めぐみ")
    assert source["provider"] == "soundcloud"
    assert source["page"] == "https://soundcloud.com/right-track"


def test_resolve_skips_unplayable_ytdlp(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    _no_bilibili(monkeypatch)
    monkeypatch.setattr(fetch, "probe_netease_url", lambda song_id: False)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/usr/bin/yt-dlp")
    monkeypatch.setattr(
        fetch,
        "_list_ytdlp",
        lambda query, ytdlp, provider, count=15: [
            {
                "url": f"https://{provider}.example/x",
                "title": "Give a reason",
                "duration": 100,
            }
        ],
    )
    monkeypatch.setattr(fetch, "_ytdlp_direct_url", lambda page: "")
    assert fetch.resolve_audio_source("1", "Give a reason", "X") == {}
    assert fetch.peek_audio_source("1") == {}


def test_resolve_uses_netease_before_youtube(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    _no_bilibili(monkeypatch)
    monkeypatch.setattr(fetch, "probe_netease_url", lambda song_id: True)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/usr/bin/yt-dlp")

    def fake_list(query, ytdlp, provider, count=15):
        if provider == "youtube":
            return [
                {
                    "url": "https://youtube.com/watch?v=x",
                    "title": "晴天",
                    "duration": 200,
                }
            ]
        return []

    monkeypatch.setattr(fetch, "_list_ytdlp", fake_list)
    monkeypatch.setattr(fetch, "_ytdlp_direct_url", lambda page: f"{page}/direct")
    source = fetch.resolve_audio_source("186016", "晴天", "周杰伦")
    assert source == {"kind": "netease", "id": "186016", "title": "晴天"}


def test_resolve_uses_youtube_last(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    _no_bilibili(monkeypatch)
    monkeypatch.setattr(fetch, "probe_netease_url", lambda song_id: False)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/usr/bin/yt-dlp")

    def fake_list(query, ytdlp, provider, count=15):
        if provider == "youtube":
            return [
                {
                    "url": "https://youtube.com/watch?v=x",
                    "title": "Give a reason",
                    "duration": 100,
                }
            ]
        return []

    monkeypatch.setattr(fetch, "_list_ytdlp", fake_list)
    monkeypatch.setattr(fetch, "_ytdlp_direct_url", lambda page: f"{page}/direct")
    source = fetch.resolve_audio_source("1", "Give a reason", "X")
    assert source["provider"] == "youtube"
