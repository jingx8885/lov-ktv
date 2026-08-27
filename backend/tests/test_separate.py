from pathlib import Path

import numpy as np

from lovktv.pipeline import separate
from lovktv.pipeline.mdx_onnx import assign_stems


def test_assign_stems_keeps_karaoke_primary_as_instrumental():
    rng = np.random.default_rng(0)
    inst = rng.normal(0, 0.4, (2, 8000)).astype(np.float32)
    voice = rng.normal(0, 0.08, (2, 8000)).astype(np.float32)
    mix = inst + voice
    vocals, instrumental = assign_stems(mix, inst, 1.0, "instrumental")
    assert float(np.mean((instrumental - inst) ** 2)) < 1e-6
    assert float(np.mean((vocals - voice) ** 2)) < 1e-6


def test_assign_stems_loud_vocal_keeps_karaoke_primary():
    rng = np.random.default_rng(2)
    inst = rng.normal(0, 0.18, (2, 8000)).astype(np.float32)
    voice = rng.normal(0, 0.55, (2, 8000)).astype(np.float32)
    mix = inst + voice
    vocals, instrumental = assign_stems(mix, inst, 1.0, "instrumental")
    assert float(np.mean((instrumental - inst) ** 2)) < 1e-6
    assert float(np.mean((vocals - voice) ** 2)) < 1e-6


def test_assign_stems_flips_wrong_vocal_hint():
    rng = np.random.default_rng(1)
    inst = rng.normal(0, 0.4, (2, 8000)).astype(np.float32)
    voice = rng.normal(0, 0.08, (2, 8000)).astype(np.float32)
    mix = inst + voice
    vocals, instrumental = assign_stems(mix, inst, 1.0, "vocals")
    assert float(np.mean((instrumental - inst) ** 2)) < 1e-6
    assert float(np.mean((vocals - voice) ** 2)) < 1e-6


def test_mdx_onnx_missing_model_returns_false(tmp_path: Path, monkeypatch):
    from lovktv.pipeline import mdx_onnx

    src = tmp_path / "original.mp3"
    src.write_bytes(b"x")
    monkeypatch.setattr(mdx_onnx, "model_path", lambda: tmp_path / "missing.onnx")
    assert mdx_onnx.separate_mdx(src, tmp_path) is False


def test_promote_separator_stems_saves_canonical_vocals(tmp_path: Path):
    (tmp_path / "original_(Vocals)_UVR_MDXNET_KARA_2.wav").write_bytes(b"VOCAL-STEM")
    (tmp_path / "original_(Instrumental)_UVR_MDXNET_KARA_2.wav").write_bytes(b"INST-STEM")
    vocals = tmp_path / "vocals.wav"
    instrumental = tmp_path / "instrumental.wav"

    assert separate.promote_separator_stems(tmp_path, vocals, instrumental) is True
    assert vocals.read_bytes() == b"VOCAL-STEM"
    assert instrumental.read_bytes() == b"INST-STEM"
    assert not list(tmp_path.glob("original_(Vocals)*"))
    assert not list(tmp_path.glob("original_(Instrumental)*"))


def test_separate_vocals_keeps_named_stem_not_original(tmp_path: Path, monkeypatch):
    src = tmp_path / "original.mp3"
    src.write_bytes(b"FULL-MIX")
    (tmp_path / "song_(Vocals)_UVR.wav").write_bytes(b"JUST-VOICE" * 400)
    (tmp_path / "song_(Instrumental)_UVR.wav").write_bytes(b"JUST-INST" * 400)
    encoded: list[tuple[str, str]] = []

    monkeypatch.setattr(separate.shutil, "which", lambda cmd: "/bin/ffmpeg")
    monkeypatch.setattr(separate, "_run_separator", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(separate, "_mean_volume_db", lambda _path: -12.0)

    def fake_ffmpeg(*args: str) -> None:
        dest = Path(args[-1])
        src_arg = Path(args[args.index("-i") + 1])
        encoded.append((src_arg.name, dest.name))
        dest.write_bytes(src_arg.read_bytes() if src_arg.exists() else b"enc")

    monkeypatch.setattr(separate, "_ffmpeg", fake_ffmpeg)

    result = separate.separate_vocals(src, tmp_path)
    assert result["degraded"] == "false"
    assert (tmp_path / "vocals.wav").read_bytes().startswith(b"JUST-VOICE")
    assert (tmp_path / "guide.m4a").read_bytes().startswith(b"JUST-VOICE")
    assert ("vocals.wav", "guide.m4a") in encoded
    assert not any(name == "original.mp3" and dest == "vocals.wav" for name, dest in encoded)


def test_separate_vocals_does_not_copy_original_as_vocals(tmp_path: Path, monkeypatch):
    src = tmp_path / "original.mp3"
    src.write_bytes(b"FULL-MIX")
    calls: list[str] = []

    monkeypatch.setattr(separate.shutil, "which", lambda cmd: "/bin/ffmpeg" if cmd == "ffmpeg" else None)

    def fake_extract(src_path: Path, dest: Path) -> None:
        calls.append("mid")
        dest.write_bytes(b"MID-VOICE")

    def fake_ffmpeg(*args: str) -> None:
        dest = Path(args[-1])
        src_arg = Path(args[args.index("-i") + 1])
        dest.write_bytes(src_arg.read_bytes() if src_arg.exists() else b"enc")

    monkeypatch.setattr(separate, "extract_center_vocals", fake_extract)
    monkeypatch.setattr(separate, "_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(separate, "_mean_volume_db", lambda _path: -12.0)

    result = separate.separate_vocals(src, tmp_path)
    assert result["degraded"] == "true"
    assert calls == ["mid"]
    assert (tmp_path / "vocals.wav").read_bytes() == b"MID-VOICE"
    assert (tmp_path / "guide.m4a").read_bytes() == b"MID-VOICE"
    assert (tmp_path / "vocals.wav").read_bytes() != src.read_bytes()
