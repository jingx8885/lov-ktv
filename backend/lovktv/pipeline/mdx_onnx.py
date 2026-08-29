"""Run UVR MDX-Net ONNX models with onnxruntime. No torch."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf

from lovktv.config import DATA_DIR, IMAGE_MODELS_DIR, WHISPER_DIR

MODEL_NAME = "UVR_MDXNET_KARA_2.onnx"
MODEL_URL = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR_MDXNET_KARA_2.onnx"
HOP = 1024

# KARA_2 is a karaoke model: the ONNX primary is instrumental, vocals = mix - primary.
MODEL_PARAMS = {
    "3a00bfec5b627a8ca6f121ea0e2a76a2": {
        "compensate": 1.035,
        "dim_f": 2048,
        "dim_t": 256,
        "n_fft": 6144,
        "primary": "instrumental",
    },
    "2f5501189a2f6db6349916fabe8c90de": {
        "compensate": 1.035,
        "dim_f": 2048,
        "dim_t": 256,
        "n_fft": 6144,
        "primary": "instrumental",
    },
    "1d64a6d2c30f709b8c9b4ce1366d96ee": {
        "compensate": 1.065,
        "dim_f": 2048,
        "dim_t": 256,
        "n_fft": 5120,
        "primary": "instrumental",
    },
}


def model_dirs() -> list[Path]:
    import os

    found: list[Path] = []
    env = (os.environ.get("LOVKTV_MODELS") or "").strip()
    if env:
        found.append(Path(env))
    found.append(IMAGE_MODELS_DIR)
    data = Path(os.environ.get("LOVKTV_DATA") or DATA_DIR)
    found.append(data / "models")
    unique: list[Path] = []
    for item in found:
        resolved = item.expanduser()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def model_path() -> Path:
    for folder in model_dirs():
        candidate = folder / MODEL_NAME
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate.resolve()
    return (model_dirs()[0] / MODEL_NAME).resolve()


def download_file(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, part)
    part.replace(dest)


def ensure_separator_model() -> Path:
    current = model_path()
    if current.exists() and current.stat().st_size > 0:
        return current
    dest = (model_dirs()[0] / MODEL_NAME).resolve()
    download_file(MODEL_URL, dest)
    return dest


def whisper_ready() -> bool:
    import os
    import shutil

    if not shutil.which("whisper"):
        return False
    root = Path(os.environ.get("LOVKTV_WHISPER_DIR") or WHISPER_DIR)
    if not root.exists():
        return False
    return any(root.glob("*.pt")) or any(root.glob("small*"))


def model_status() -> dict[str, object]:
    path = model_path()
    ready = path.exists() and path.stat().st_size > 0
    return {
        "separator": ready,
        "separator_path": str(path) if ready else "",
        "whisper": whisper_ready(),
    }


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hann(n_fft: int) -> np.ndarray:
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft, dtype=np.float32) / n_fft)


def _stft(wave: np.ndarray, n_fft: int, hop: int, dim_f: int) -> np.ndarray:
    """Match torch.stft(center=True, return_complex=False, periodic Hann). wave is [2, T]."""
    window = _hann(n_fft)
    pad = n_fft // 2
    padded = np.pad(wave, ((0, 0), (pad, pad)), mode="reflect")
    frames = 1 + (padded.shape[1] - n_fft) // hop
    spec = np.zeros((4, dim_f, frames), dtype=np.float32)
    for channel in range(2):
        for index in range(frames):
            start = index * hop
            frame = padded[channel, start : start + n_fft] * window
            bins = np.fft.rfft(frame, n=n_fft)
            spec[channel * 2, :, index] = bins.real[:dim_f]
            spec[channel * 2 + 1, :, index] = bins.imag[:dim_f]
    return spec


def _istft(spec: np.ndarray, n_fft: int, hop: int, length: int) -> np.ndarray:
    """Inverse of _stft. spec is [4, dim_f, frames] or [1, 4, dim_f, frames]."""
    if spec.ndim == 4:
        spec = spec[0]
    dim_f, frames = spec.shape[1], spec.shape[2]
    n_bins = n_fft // 2 + 1
    window = _hann(n_fft)
    wave = np.zeros((2, hop * (frames - 1) + n_fft), dtype=np.float32)
    acc = np.zeros_like(wave)
    for channel in range(2):
        for index in range(frames):
            bins = np.zeros(n_bins, dtype=np.complex64)
            bins.real[:dim_f] = spec[channel * 2, :, index]
            bins.imag[:dim_f] = spec[channel * 2 + 1, :, index]
            frame = np.fft.irfft(bins, n=n_fft).real * window
            start = index * hop
            wave[channel, start : start + n_fft] += frame
            acc[channel, start : start + n_fft] += window**2
    acc = np.maximum(acc, 1e-8)
    wave /= acc
    pad = n_fft // 2
    return wave[:, pad : pad + length]


def _load_stereo(path: Path, sr: int = 44100) -> tuple[np.ndarray, int]:
    if path.suffix.lower() not in {".wav", ".flac"}:
        import subprocess

        raw = path.with_name(path.stem + f".{sr}.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-ac", "2", "-ar", str(sr), str(raw)],
            check=True,
            timeout=180,
            capture_output=True,
        )
        wave, file_sr = _load_stereo(raw, sr)
        raw.unlink(missing_ok=True)
        return wave, file_sr
    audio, file_sr = sf.read(str(path), always_2d=True, dtype="float32")
    wave = audio.T
    if wave.shape[0] == 1:
        wave = np.vstack([wave, wave])
    elif wave.shape[0] > 2:
        wave = wave[:2]
    if file_sr != sr:
        import subprocess

        raw = path.with_name(path.stem + f".{sr}.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-ac", "2", "-ar", str(sr), str(raw)],
            check=True,
            timeout=180,
            capture_output=True,
        )
        wave, file_sr = _load_stereo(raw, sr)
        raw.unlink(missing_ok=True)
    return wave.astype(np.float32), file_sr


def _corr(left: np.ndarray, right: np.ndarray) -> float:
    a = left.mean(axis=0) if left.ndim == 2 else left
    b = right.mean(axis=0) if right.ndim == 2 else right
    n = min(a.size, b.size)
    a = a[:n] - float(a[:n].mean())
    b = b[:n] - float(b[:n].mean())
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 1e-12 else 0.0


def assign_stems(
    mix: np.ndarray, primary: np.ndarray, compensate: float, hint: str = "instrumental"
) -> tuple[np.ndarray, np.ndarray]:
    """Return (vocals, instrumental). Karaoke models emit the backing track as primary."""
    residual = mix - primary * compensate
    if hint == "instrumental":
        return residual, primary
    primary_like = _corr(primary, mix)
    residual_like = _corr(residual, mix)
    if abs(primary_like - residual_like) < 0.05:
        primary_is_mix = False
    else:
        primary_is_mix = primary_like > residual_like
    if primary_is_mix:
        return residual, primary
    return primary, residual


def separate_mdx(src: Path, out_dir: Path, onnx_path: Path | None = None) -> bool:
    """Write vocals.wav and instrumental.wav. Returns False if the ONNX model is missing."""
    try:
        import onnxruntime as ort
    except ImportError:
        return False
    onnx_path = Path(onnx_path or model_path())
    if not onnx_path.exists():
        return False
    params = MODEL_PARAMS.get(
        _md5(onnx_path), MODEL_PARAMS["2f5501189a2f6db6349916fabe8c90de"]
    )
    n_fft = int(params["n_fft"])
    dim_f = int(params["dim_f"])
    dim_t = int(params["dim_t"])
    compensate = float(params["compensate"])
    mix, sr = _load_stereo(src)
    peak = float(np.max(np.abs(mix)) or 1.0)
    mix = mix / peak
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    trim = n_fft // 2
    chunk = HOP * (dim_t - 1)
    gen = chunk - 2 * trim
    overlap = 0.25
    step = int((1 - overlap) * chunk)
    pad = gen + trim - (mix.shape[-1] % gen)
    mixture = np.concatenate(
        (np.zeros((2, trim), np.float32), mix, np.zeros((2, pad), np.float32)),
        axis=1,
    )
    result = np.zeros((2, mixture.shape[-1]), np.float32)
    weight = np.zeros_like(result)
    name = session.get_inputs()[0].name
    for start in range(0, mixture.shape[-1], step):
        end = min(start + chunk, mixture.shape[-1])
        part = mixture[:, start:end]
        if part.shape[1] < chunk:
            part = np.pad(part, ((0, 0), (0, chunk - part.shape[1])))
        window = np.hanning(end - start).astype(np.float32)
        spec = _stft(part, n_fft, HOP, dim_f)[None]
        spec[:, :, :3, :] = 0
        pred = session.run(None, {name: spec})[0]
        wave = _istft(pred, n_fft, HOP, part.shape[1])
        span = end - start
        result[:, start:end] += wave[:, :span] * window
        weight[:, start:end] += window
    primary = (result / np.maximum(weight, 1e-8))[:, trim : trim + mix.shape[1]] * peak
    vocals, inst = assign_stems(mix * peak, primary, compensate, str(params["primary"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    sf.write(out_dir / "vocals.wav", vocals.T, sr, subtype="FLOAT")
    sf.write(out_dir / "instrumental.wav", inst.T, sr, subtype="FLOAT")
    return True
