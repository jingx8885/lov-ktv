from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

STEM_AUDIO = {".wav", ".flac", ".mp3", ".m4a", ".ogg"}


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", *args], check=True, timeout=180, capture_output=True)


def _mean_volume_db(path: Path) -> float:
    result = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    for line in (result.stderr or "").splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].split("dB")[0].strip())
            except ValueError:
                return -99.0
    return -99.0


def named_stem(out_dir: Path, label: str) -> Path | None:
    """Pick the newest audio-separator file such as song_(Vocals)_MODEL.wav."""
    key = f"({label})".lower()
    hits = [
        path
        for path in out_dir.iterdir()
        if path.is_file() and path.suffix.lower() in STEM_AUDIO and key in path.name.lower()
    ]
    if not hits:
        return None
    hits.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return hits[0]


def save_stem_wav(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dest.resolve():
        return dest
    if src.suffix.lower() == ".wav":
        shutil.copy2(src, dest)
    else:
        _ffmpeg("-i", str(src), str(dest))
    if src.resolve() != dest.resolve() and src.name != dest.name:
        src.unlink(missing_ok=True)
    return dest


def promote_separator_stems(out_dir: Path, vocals: Path, instrumental: Path) -> bool:
    """Keep UVR stems as vocals.wav / instrumental.wav instead of leaving long model names."""
    found = False
    vocal_src = named_stem(out_dir, "Vocals")
    inst_src = named_stem(out_dir, "Instrumental")
    if vocal_src:
        save_stem_wav(vocal_src, vocals)
        found = True
    if inst_src:
        save_stem_wav(inst_src, instrumental)
        found = True
    return found


def extract_center_vocals(src: Path, dest: Path) -> None:
    """Degraded vocal stem: keep the mid, drop the sides. Not a full UVR isolate."""
    _ffmpeg(
        "-i",
        str(src),
        "-af",
        "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1",
        str(dest),
    )


def _run_separator(src: Path, out_dir: Path) -> None:
    from lovktv.pipeline.mdx_onnx import separate_mdx

    try:
        if separate_mdx(src, out_dir):
            return
    except Exception:
        pass
    cmd = shutil.which("audio-separator")
    if not cmd:
        return
    subprocess.run(
        [
            cmd,
            str(src),
            "--output_dir",
            str(out_dir),
            "--output_format",
            "WAV",
            "--model_filename",
            "UVR_MDXNET_KARA_2.onnx",
            "--custom_output_names",
            json.dumps({"Vocals": "vocals", "Instrumental": "instrumental"}),
        ],
        check=True,
        timeout=600,
    )


def separate_vocals(src: Path, out_dir: Path) -> dict[str, str]:
    """Create instrumental + vocals, then always persist them as canonical filenames."""
    out_dir.mkdir(parents=True, exist_ok=True)
    instrumental = out_dir / "instrumental.wav"
    vocals = out_dir / "vocals.wav"
    karaoke = out_dir / "karaoke.m4a"
    guide = out_dir / "guide.m4a"
    if not shutil.which("ffmpeg"):
        raise RuntimeError("需要 ffmpeg 才能封装伴奏/人声")

    degraded = False
    _run_separator(src, out_dir)
    if promote_separator_stems(out_dir, vocals, instrumental):
        pass
    elif not vocals.exists():
        extract_center_vocals(src, vocals)
        degraded = True

    if not instrumental.exists():
        karaoke_src = src
        degraded = True
    else:
        karaoke_src = instrumental
        if _mean_volume_db(instrumental) < -40:
            karaoke_src = src
            degraded = True

    _ffmpeg("-i", str(karaoke_src), "-c:a", "aac", "-b:a", "192k", str(karaoke))
    if not karaoke.exists() or karaoke.stat().st_size < 2048:
        _ffmpeg("-i", str(src), "-c:a", "aac", "-b:a", "192k", str(karaoke))
        degraded = True
    if not vocals.exists():
        raise RuntimeError("人声轨没有保存下来")
    _ffmpeg("-i", str(vocals), "-c:a", "aac", "-b:a", "192k", str(guide))
    return {
        "instrumental": instrumental.name,
        "vocals": vocals.name,
        "karaoke": karaoke.name,
        "guide": guide.name,
        "degraded": "true" if degraded else "false",
    }
