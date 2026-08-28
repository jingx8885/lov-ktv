import json

from lovktv.catalog import fetch, netease


def test_eapi_params_roundtrip_with_openssl():
    payload = {"ids": "[33894312]", "br": 320000}
    blob = netease.eapi_params(payload)
    assert blob.isupper()
    assert len(blob) >= 32
    plain = __import__("subprocess").run(
        ["openssl", "enc", "-aes-128-ecb", "-d", "-K", netease.EAPI_KEY.hex(), "-nosalt"],
        input=bytes.fromhex(blob),
        capture_output=True,
        check=True,
    ).stdout
    assert b"/api/song/enhance/player/url" in plain
    assert b"33894312" in plain


def test_probe_uses_eapi_url(monkeypatch):
    monkeypatch.setattr(netease, "eapi_play_url", lambda song_id: "http://m8.music.126.net/x.mp3")
    monkeypatch.setattr(fetch, "eapi_play_url", lambda song_id: "http://m8.music.126.net/x.mp3")
    assert fetch.probe_netease_url("33894312") is True
    monkeypatch.setattr(fetch, "eapi_play_url", lambda song_id: "")
    assert fetch.probe_netease_url("186016") is False


def test_eapi_play_url_reads_cdn(monkeypatch):
    class FakeResp:
        def read(self):
            return json.dumps(
                {"data": [{"id": 33894312, "url": "http://m8.music.126.net/ok.mp3", "code": 200}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(netease, "urlopen", lambda req, timeout=12, via_proxy=True: FakeResp())
    assert netease.eapi_play_url("33894312") == "http://m8.music.126.net/ok.mp3"


def test_eapi_play_url_empty_on_404(monkeypatch):
    class FakeResp:
        def read(self):
            return json.dumps({"data": [{"id": 186016, "url": None, "code": 404}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(netease, "urlopen", lambda req, timeout=12, via_proxy=True: FakeResp())
    assert netease.eapi_play_url("186016") == ""


def test_download_uses_eapi_cdn_and_proxy(monkeypatch, tmp_path):
    monkeypatch.setenv("LOVKTV_HTTPS_PROXY", "http://clash:7890")
    monkeypatch.setattr(fetch, "eapi_play_url", lambda song_id: "http://m8.music.126.net/ok.mp3")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        dest = tmp_path / "a.mp3"
        dest.write_bytes(b"x" * 60_000)

        class Result:
            stdout = "200\nhttp://m8.music.126.net/ok.mp3\n"

        return Result()

    monkeypatch.setattr(fetch.subprocess, "run", fake_run)
    assert fetch.try_netease_download("33894312", tmp_path / "a.mp3") is True
    assert "http://m8.music.126.net/ok.mp3" in seen["cmd"]
    assert "music.163.com/song/media/outer" not in " ".join(seen["cmd"])
    assert seen["cmd"][seen["cmd"].index("-x") + 1] == "http://clash:7890"
