from lovktv.media import host_volume


def test_set_host_volume_skipped_off_mac(monkeypatch):
    host_volume._cached = None
    host_volume._cached_at = 0
    monkeypatch.setattr(host_volume, "is_mac", lambda: False)
    assert host_volume.set_host_volume(40) is False
    assert host_volume.get_host_volume() is None
    assert host_volume.host_volume_meta() == {}


def test_set_host_volume_runs_osascript(monkeypatch):
    host_volume._cached = None
    host_volume._cached_at = 0
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return None

    monkeypatch.setattr(host_volume, "is_mac", lambda: True)
    monkeypatch.setattr(host_volume.subprocess, "run", fake_run)
    assert host_volume.set_host_volume(150) is True
    assert calls[0][:2] == ["osascript", "-e"]
    assert "output volume 100" in calls[0][2]
    assert host_volume.get_host_volume() == 100
    assert host_volume.host_volume_meta()["host_volume_kind"] == "mac"
    assert host_volume.host_volume_meta()["host_volume"] == 100


def test_get_host_volume_reads_osascript(monkeypatch):
    host_volume._cached = None
    host_volume._cached_at = 0
    monkeypatch.setattr(host_volume, "is_mac", lambda: True)
    monkeypatch.setattr(
        host_volume.subprocess,
        "check_output",
        lambda *args, **kwargs: "42\n",
    )
    assert host_volume.get_host_volume() == 42
    assert host_volume.get_host_volume() == 42
