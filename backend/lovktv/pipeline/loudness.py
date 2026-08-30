"""Normalize playable karaoke/original to a loud KTV level.

Commercial pop like Stay sits around -9 LUFS. Quieter imports get lifted
to that so the phone mic can sit next to the track.
"""

from __future__ import annotations

from pathlib import Path

# Integrated loudness of a loud pop mix (Stay / similar). YouTube is -14.
KTV_LUFS = -9.0
KTV_TRUE_PEAK = -1.5
KTV_LRA = 11.0

LOUDNORM_FILTER = f"loudnorm=I={KTV_LUFS}:TP={KTV_TRUE_PEAK}:LRA={KTV_LRA}"


def loudnorm_args() -> list[str]:
    return ["-af", LOUDNORM_FILTER]


def normalize_file(path: Path) -> bool:
    """Rewrite a playable mp3/m4a in place to KTV_LUFS. False if ffmpeg skipped."""
    import shutil
    import subprocess

    if not path.exists() or not shutil.which("ffmpeg"):
        return False
    suffix = path.suffix.lower()
    if suffix == ".m4a":
        codec = ["-c:a", "aac", "-b:a", "192k"]
    elif suffix == ".mp3":
        codec = ["-c:a", "libmp3lame", "-q:a", "2"]
    else:
        return False
    tmp = path.with_name(path.name + ".loud")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), *loudnorm_args(), *codec, str(tmp)],
            check=True,
            timeout=180,
            capture_output=True,
        )
        if tmp.exists() and tmp.stat().st_size > 2048:
            tmp.replace(path)
            return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return False
