import hashlib

from lovktv.catalog import audio, bilibili, fetch


def test_score_rejects_title_inside_longer_name():
    official = {
        "title": "周杰伦-晴天[正版]",
        "typename": "MV",
        "duration": 316,
        "author": "杰威尔音乐",
    }
    other = {
        "title": "孙燕姿.明天晴天.MV",
        "typename": "MV",
        "duration": 240,
        "author": "x",
    }
    assert bilibili.score_hit(official, "晴天", "") >= 0
    assert bilibili.score_hit(other, "晴天", "") == -1


def test_wbi_sign_is_stable():
    signed = bilibili.sign_wbi(
        {"keyword": "晴天", "search_type": "video"},
        "7cd084941338484aae1ad9425b84077c",
        "4932caff0ff746eab6f01bf08b70ac45",
        ts=1700000000,
    )
    assert signed["wts"] == 1700000000
    assert (
        signed["w_rid"]
        == hashlib.md5(
            (
                "keyword=%E6%99%B4%E5%A4%A9&search_type=video&wts=1700000000"
                + bilibili.mixin_key(
                    "7cd084941338484aae1ad9425b84077c",
                    "4932caff0ff746eab6f01bf08b70ac45",
                )
            ).encode()
        ).hexdigest()
    )


def test_video_items_reads_all_v2_block():
    items = bilibili._video_items(
        {
            "code": 0,
            "data": {
                "result": [
                    {"result_type": "tips", "data": []},
                    {
                        "result_type": "video",
                        "data": [
                            {
                                "bvid": "BV1xx",
                                "title": "晴天",
                                "author": "x",
                                "duration": "4:30",
                            }
                        ],
                    },
                ]
            },
        }
    )
    assert items[0]["bvid"] == "BV1xx"


def test_search_videos_falls_back_when_wbi_empty(monkeypatch):
    monkeypatch.setattr(bilibili, "_search_wbi", lambda *args, **kwargs: [])
    monkeypatch.setattr(bilibili, "_search_type", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        bilibili,
        "_search_all",
        lambda query, page: [
            {
                "bvid": "BV1UZhK61E9z",
                "title": "<em>晴天</em>",
                "author": "杰威尔",
                "duration": "5:16",
                "pic": "",
            }
        ],
    )
    monkeypatch.setattr(bilibili.time, "sleep", lambda _s: None)
    hits = bilibili.search_videos("晴天")
    assert hits[0]["bvid"] == "BV1UZhK61E9z"
    assert hits[0]["title"] == "晴天"


def test_is_bvid():
    assert bilibili.is_bvid("BV1UZhK61E9z")
    assert not bilibili.is_bvid("186016")
    assert not bilibili.is_bvid("not-a-bvid")


def test_strip_title_and_duration():
    assert bilibili.strip_title('<em class="keyword">晴天</em> 正版MV') == "晴天 正版MV"
    assert bilibili.parse_duration("5:16") == 316
    assert bilibili.parse_duration("1:05:16") == 3916
    assert bilibili.parse_duration(240) == 240
    assert bilibili.parse_duration("NA") is None
    assert (
        bilibili.cover_url("//i0.hdslb.com/bfs/x.jpg")
        == "https://i0.hdslb.com/bfs/x.jpg"
    )


def test_score_prefers_official_mv():
    official = {
        "title": "周杰伦-晴天[正版]",
        "typename": "MV",
        "duration": 316,
        "author": "杰威尔音乐",
    }
    compilation = {
        "title": "周杰伦晴天合集 8小时",
        "typename": "音乐综合",
        "duration": 50_700,
        "author": "x",
    }
    cover = {
        "title": "晴天 翻唱 cover",
        "typename": "翻唱",
        "duration": 280,
        "author": "x",
    }
    other = {
        "title": "ただ君に晴れ (只给予你的晴天) MV",
        "typename": "MV",
        "duration": 200,
        "author": "ヨルシカ",
    }
    assert bilibili.score_hit(official, "晴天", "周杰伦") >= 120
    assert bilibili.score_hit(compilation, "晴天", "周杰伦") == -1
    assert bilibili.score_hit(cover, "晴天", "周杰伦") == -1
    assert bilibili.score_hit(other, "晴天", "周杰伦") == -1


def test_pick_mv_uses_ranked_search(monkeypatch):
    monkeypatch.setattr(
        bilibili,
        "search_videos",
        lambda query, count=20: [
            {
                "bvid": "BV1long",
                "title": "晴天 合集",
                "typename": "音乐综合",
                "duration": 50_000,
                "author": "x",
                "pic": "",
                "page": "https://www.bilibili.com/video/BV1long",
            },
            {
                "bvid": "BV1UZhK61E9z",
                "title": "周杰伦-晴天[正版]",
                "typename": "MV",
                "duration": 316,
                "author": "杰威尔音乐",
                "pic": "https://i0.hdslb.com/bfs/x.jpg",
                "page": "https://www.bilibili.com/video/BV1UZhK61E9z",
            },
        ],
    )
    hit = bilibili.pick_mv("晴天", "周杰伦")
    assert hit["bvid"] == "BV1UZhK61E9z"


def test_resolve_retries_bilibili_over_cached_youtube(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    fetch.remember_audio_source(
        "186016",
        {
            "kind": "ytdlp",
            "page": "https://youtube.com/watch?v=wrong",
            "title": "花海 DJ",
            "provider": "youtube",
        },
    )
    monkeypatch.setattr(audio, "probe_netease_url", lambda song_id: False)
    monkeypatch.setattr(
        fetch,
        "pick_bilibili_mv",
        lambda title, artist="": {
            "bvid": "BV1UZhK61E9z",
            "title": "周杰伦-晴天[正版]",
            "pic": "",
        },
    )
    monkeypatch.setattr(
        audio.bilibili,
        "play_urls",
        lambda bvid: {"audio_url": "https://upos.example/a.m4s"},
    )
    source = fetch.resolve_audio_source("186016", "晴天", "周杰伦")
    assert source["kind"] == "bilibili"
    assert source["bvid"] == "BV1UZhK61E9z"


def test_resolve_uses_netease_before_bilibili(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    monkeypatch.setattr(
        fetch,
        "pick_bilibili_mv",
        lambda title, artist="": {
            "bvid": "BV1UZhK61E9z",
            "title": "周杰伦-晴天[正版]",
            "pic": "",
        },
    )
    monkeypatch.setattr(
        audio.bilibili,
        "play_urls",
        lambda bvid: {"audio_url": "https://upos.example/a.m4s"},
    )
    monkeypatch.setattr(audio, "probe_netease_url", lambda song_id: True)
    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/yt-dlp")
    source = fetch.resolve_audio_source("186016", "晴天", "周杰伦")
    assert source["kind"] == "netease"
    assert source["id"] == "186016"


def test_resolve_retries_cleaned_title_on_bilibili(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    seen = []

    def fake_pick(title, artist=""):
        seen.append((title, artist))
        if title == "晴天":
            return {"bvid": "BV1UZhK61E9z", "title": "周杰伦-晴天[正版]", "pic": ""}
        return None

    monkeypatch.setattr(audio, "probe_netease_url", lambda song_id: False)
    monkeypatch.setattr(fetch, "pick_bilibili_mv", fake_pick)
    monkeypatch.setattr(
        audio.bilibili,
        "play_urls",
        lambda bvid: {"audio_url": "https://upos.example/a.m4s"},
    )
    source = fetch.resolve_audio_source("2652820720", "晴天(深情版)", "Lucky小爱")
    assert ("晴天(深情版)", "Lucky小爱") in seen
    assert ("晴天", "") in seen
    assert source["bvid"] == "BV1UZhK61E9z"


def test_resolve_uses_bilibili_when_netease_empty(monkeypatch):
    fetch._AUDIO_CACHE.clear()
    monkeypatch.setattr(audio, "probe_netease_url", lambda song_id: False)
    monkeypatch.setattr(
        fetch,
        "pick_bilibili_mv",
        lambda title, artist="": {
            "bvid": "BV1UZhK61E9z",
            "title": "周杰伦-晴天[正版]",
            "pic": "",
        },
    )
    monkeypatch.setattr(
        audio.bilibili,
        "play_urls",
        lambda bvid: {"audio_url": "https://upos.example/a.m4s"},
    )
    source = fetch.resolve_audio_source("2652820720", "晴天(深情版)", "Lucky小爱")
    assert source["kind"] == "bilibili"
    assert source["bvid"] == "BV1UZhK61E9z"


def test_import_uses_bilibili_before_soundcloud(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fetch,
        "search_mugen",
        lambda query, count=10, page=1: {"hits": [], "has_more": False, "total": 0},
    )
    monkeypatch.setattr(fetch, "is_mugen_kid", lambda value: False)
    monkeypatch.setattr(fetch, "fetch_kugou_lyrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        fetch,
        "search_tonzhon",
        lambda *args, **kwargs: [
            {"id": "186016", "name": "晴天", "artist": ["周杰伦"]}
        ],
    )
    monkeypatch.setattr(
        fetch, "fetch_lyric", lambda song_id, source="netease": "[00:01.00]故事的小黄花"
    )
    monkeypatch.setattr(
        fetch,
        "pick_bilibili_mv",
        lambda title, artist="": {
            "bvid": "BV1UZhK61E9z",
            "title": "周杰伦-晴天[正版]",
            "pic": "",
        },
    )

    def fake_download(bvid, mp3_path, video_path=None):
        mp3_path.write_bytes(b"x" * 60_000)
        if video_path is not None:
            video_path.write_bytes(b"v" * 2000)
        return True

    monkeypatch.setattr(fetch, "try_bilibili_download", fake_download)
    monkeypatch.setattr(
        fetch,
        "try_ytdlp_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ytdlp")),
    )
    monkeypatch.setattr(
        fetch,
        "try_netease_download",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("netease")),
    )
    skeleton = fetch.import_song(query="晴天", out_dir=tmp_path, song_id="186016")
    assert skeleton["audio"]["source"] == "bilibili"
    assert skeleton["has_video"] is True
    assert skeleton["source"]["bvid"] == "BV1UZhK61E9z"
    assert (tmp_path / "mtv.mp4").exists()
