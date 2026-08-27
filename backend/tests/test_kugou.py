import base64
import zlib

from lovktv.catalog import fetch, kugou


KRC_SAMPLE = """[ti:晴天]
[ar:周杰伦]
[offset:0]
[1707,960]<0,202,0>周<202,608,0>杰<810,0,0>伦 <810,51,0>- <861,49,0>晴<910,50,0>天
[2667,660]<0,0,0>作<0,51,0>词<51,51,0>：<102,0,0>周<102,355,0>杰<457,203,0>伦
[29269,2884]<0,354,0>故<354,401,0>事<755,458,0>的<1213,860,0>小<2073,405,0>黄<2478,406,0>花
[32660,3044]<0,405,0>从<405,403,0>出<808,462,0>生<1270,455,0>那<1725,354,0>年
"""


def _encode_krc(text: str) -> str:
    payload = zlib.compress(b"\xef\xbb\xbf" + text.encode("utf-8"))
    encrypted = bytes(byte ^ kugou.KRC_KEY[index % 16] for index, byte in enumerate(payload))
    return base64.b64encode(b"krc1" + encrypted).decode("ascii")


def test_decode_and_parse_krc_skips_credits():
    raw = kugou.decode_krc(_encode_krc(KRC_SAMPLE))
    cues = kugou.parse_krc(raw, title="晴天", artist="周杰伦")
    assert [cue["text"] for cue in cues] == ["故事的小黄花", "从出生那年"]
    first = cues[0]["tokens"]
    assert "".join(tok["text"] for tok in first) == "故事的小黄花"
    assert first[0]["start_ms"] == 29269
    assert first[0]["end_ms"] == 29269 + 354


def test_pick_candidate_prefers_official():
    chosen = kugou.pick_candidate(
        [
            {"id": "1", "accesskey": "a", "score": 60, "product_from": "第三方歌词", "song": "晴天", "singer": "周杰伦", "duration": 269000},
            {"id": "2", "accesskey": "b", "score": 50, "product_from": "官方推荐歌词", "song": "晴天", "singer": "周杰伦", "duration": 265000},
        ],
        title="晴天",
        artist="周杰伦",
        duration_ms=265000,
    )
    assert chosen["id"] == "2"


def test_fetch_kugou_lyrics_builds_timeline(monkeypatch):
    monkeypatch.setattr(
        kugou,
        "search_kugou_lyrics",
        lambda keyword, duration_ms=0: [
            {"id": "2", "accesskey": "b", "score": 50, "product_from": "官方推荐歌词", "song": "晴天", "singer": "周杰伦"}
        ],
    )
    monkeypatch.setattr(kugou, "download_kugou_krc", lambda candidate: KRC_SAMPLE)
    got = kugou.fetch_kugou_lyrics("晴天", "周杰伦")
    assert got is not None
    assert got["timeline"]["alignment_source"] == "kugou-krc"
    assert got["timeline"]["language"] == "zh"
    assert got["candidate"]["id"] == "2"
    assert "故事的小黄花" in got["lrc"]


def test_import_song_uses_kugou_lyrics(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fetch,
        "search_mugen",
        lambda query, count=10, page=1: {"hits": [], "has_more": False, "total": 0},
    )
    monkeypatch.setattr(fetch, "is_mugen_kid", lambda value: False)
    monkeypatch.setattr(
        fetch,
        "search_tonzhon",
        lambda *args, **kwargs: [{"id": "1", "name": "晴天", "artist": ["周杰伦"]}],
    )
    monkeypatch.setattr(
        fetch,
        "fetch_kugou_lyrics",
        lambda title, artist="", duration_ms=0, language=None: {
            "timeline": {
                "language": "zh",
                "alignment": "kugou",
                "alignment_source": "kugou-krc",
                "cues": [
                    {
                        "text": "故事的小黄花",
                        "start_ms": 29269,
                        "end_ms": 32153,
                        "tokens": [{"text": "故", "start_ms": 29269, "end_ms": 29623, "reading": ""}],
                    }
                ],
            },
            "lrc": "[00:29.269]故事的小黄花\n",
            "candidate": {"id": "kg1", "song": "晴天", "singer": "周杰伦"},
        },
    )
    monkeypatch.setattr(fetch, "fetch_lyric", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("netease lyric should not run")))
    monkeypatch.setattr(fetch, "try_netease_download", lambda song_id, path: path.write_bytes(b"x" * 60_000) or True)
    monkeypatch.setattr(fetch, "try_ytdlp_search", lambda *args, **kwargs: (False, ""))
    skeleton = fetch.import_song(query="晴天", out_dir=tmp_path, song_id="1")
    assert skeleton["needs_align"] is False
    assert skeleton["source"]["lyrics"] == "kugou"
    assert skeleton["language"] == "zh"
    assert "故事的小黄花" in (tmp_path / "lyrics.lrc").read_text(encoding="utf-8")
    assert "kugou-krc" in (tmp_path / "lyrics.json").read_text(encoding="utf-8")


def test_import_song_falls_back_to_netease_lyrics(tmp_path, monkeypatch):
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
        lambda *args, **kwargs: [{"id": "22689669", "name": "Give a reason", "artist": ["林原めぐみ"]}],
    )
    monkeypatch.setattr(fetch, "fetch_lyric", lambda song_id, source="netease": "[00:01.00]Give a reason")
    monkeypatch.setattr(fetch, "try_netease_download", lambda song_id, path: path.write_bytes(b"x" * 60_000) or True)
    monkeypatch.setattr(fetch, "try_ytdlp_search", lambda *args, **kwargs: (False, ""))
    skeleton = fetch.import_song(query="Give a reason", out_dir=tmp_path, song_id="22689669")
    assert skeleton["needs_align"] is True
    assert skeleton["source"]["lyrics"] == "netease"
    assert (tmp_path / "lyrics.lrc").read_text(encoding="utf-8").startswith("[00:01.00]")
