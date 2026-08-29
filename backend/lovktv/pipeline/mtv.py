"""Classic MTV compose, adapted from qiaomu-mtv-creator.

Server-side path: lyric-timed scenes → atmospheric stills → FFmpeg xfade.
Subtitles stay external (KTV overlay). HyperFrames/GSAP is agent-only and
is not run during song import.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

WIDTH = 1920
HEIGHT = 1080
MIN_SCENE_MS = 3500
MAX_SCENE_MS = 8000
MAX_SCENES = 14
TRANSITIONS = {
    "cinematic": ("fade", "dissolve", "fadeblack", "slideup"),
    "dream": ("fade", "circleopen", "dissolve", "fadewhite"),
    "poster": ("wipeleft", "wiperight", "slideup", "fade"),
    "glitch": ("hlslice", "distance", "zoomin", "vertopen"),
    "minimal": ("fade", "fade", "dissolve", "fade"),
}

PROFILES = {
    "cinematic": {
        "style": "coldwave cinematic stills",
        "colors": [
            ("#0b1020", "#2a1848"),
            ("#101828", "#3d2a1a"),
            ("#12101c", "#1c3a4a"),
        ],
    },
    "dream": {
        "style": "soft bloom night haze",
        "colors": [
            ("#1a1030", "#3a5a7a"),
            ("#201028", "#4a3070"),
            ("#102030", "#2a6070"),
        ],
    },
    "poster": {
        "style": "warm poster grain",
        "colors": [
            ("#2a1810", "#8a3a20"),
            ("#201810", "#6a4020"),
            ("#301810", "#a05030"),
        ],
    },
    "glitch": {
        "style": "neon signal scan",
        "colors": [
            ("#081018", "#00c8c8"),
            ("#100818", "#c02080"),
            ("#081010", "#40f0a0"),
        ],
    },
    "minimal": {
        "style": "quiet paper light",
        "colors": [
            ("#16141a", "#3a3840"),
            ("#141820", "#2a3038"),
            ("#1a1814", "#3a3428"),
        ],
    },
}

_DREAM = re.compile(r"雨|雾|夢|梦|海|风|風|夜|moon|rain|dream|haze|glass", re.I)
_GLITCH = re.compile(r"电|電|霓虹|赛博|信號|信号|glitch|neon|cyber|radio", re.I)
_POSTER = re.compile(r"爱|愛|花|红|紅|暖|heart|love|red|summer", re.I)


def pick_profile(title: str, lyrics: str) -> str:
    blob = f"{title}\n{lyrics}"
    if _GLITCH.search(blob):
        return "glitch"
    if _DREAM.search(blob):
        return "dream"
    if _POSTER.search(blob):
        return "poster"
    if len(lyrics.strip()) < 8:
        return "minimal"
    return "cinematic"


def group_scenes(
    cues: list[dict[str, Any]],
    duration_ms: int,
    min_ms: int = MIN_SCENE_MS,
    max_ms: int = MAX_SCENE_MS,
    max_scenes: int = MAX_SCENES,
) -> list[dict[str, Any]]:
    if not cues:
        end = max(duration_ms, min_ms)
        return [{"index": 1, "start_ms": 0, "end_ms": end, "text": "", "lines": []}]

    scenes: list[dict[str, Any]] = []
    bucket: list[dict[str, Any]] = []
    start_ms = int(cues[0]["start_ms"])
    if start_ms > 400:
        scenes.append(
            {
                "index": 0,
                "start_ms": 0,
                "end_ms": start_ms,
                "text": "",
                "lines": [],
                "kind": "title",
            }
        )
    for cue in cues:
        if bucket and int(cue["start_ms"]) - int(bucket[-1]["end_ms"]) >= 2500:
            end_ms = int(bucket[-1]["end_ms"])
            scenes.append(_scene_from_bucket(len(scenes) + 1, start_ms, end_ms, bucket))
            bucket = []
        if not bucket:
            start_ms = int(cue["start_ms"])
        bucket.append(cue)
        end_ms = int(cue["end_ms"])
        span = end_ms - start_ms
        if span >= min_ms and (span >= max_ms or len(bucket) >= 3):
            scenes.append(_scene_from_bucket(len(scenes) + 1, start_ms, end_ms, bucket))
            bucket = []
            start_ms = end_ms
    if bucket:
        end_ms = max(int(bucket[-1]["end_ms"]), start_ms + min_ms)
        if scenes and end_ms - scenes[-1]["end_ms"] < min_ms:
            scenes[-1]["end_ms"] = end_ms
            scenes[-1]["lines"].extend(item.get("text") or "" for item in bucket)
            scenes[-1]["text"] = " / ".join(
                part for part in scenes[-1]["lines"] if part
            )[:80]
        else:
            scenes.append(_scene_from_bucket(len(scenes) + 1, start_ms, end_ms, bucket))

    while len(scenes) > max_scenes:
        idx = min(
            range(len(scenes) - 1),
            key=lambda i: scenes[i]["end_ms"] - scenes[i]["start_ms"],
        )
        nxt = scenes[idx + 1]
        scenes[idx]["end_ms"] = nxt["end_ms"]
        scenes[idx]["lines"].extend(nxt["lines"])
        scenes[idx]["text"] = " / ".join(part for part in scenes[idx]["lines"] if part)[
            :80
        ]
        del scenes[idx + 1]
    for index, scene in enumerate(scenes, start=1):
        scene["index"] = index
    if scenes and duration_ms:
        scenes[-1]["end_ms"] = max(scenes[-1]["end_ms"], duration_ms)
    return scenes


def _scene_from_bucket(
    index: int, start_ms: int, end_ms: int, bucket: list[dict[str, Any]]
) -> dict[str, Any]:
    lines = [str(item.get("text") or "") for item in bucket if item.get("text")]
    return {
        "index": index,
        "start_ms": start_ms,
        "end_ms": max(start_ms + MIN_SCENE_MS, end_ms),
        "text": " / ".join(lines)[:80],
        "lines": lines,
        "kind": "lyric",
    }


def write_project_files(
    out_dir: Path,
    *,
    title: str,
    artist: str,
    profile: str,
    scenes: list[dict[str, Any]],
    duration_ms: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = PROFILES[profile]
    visual = {
        "title": title,
        "artist": artist,
        "ratio": "16:9",
        "motion_profile": profile,
        "style": spec["style"],
        "burn_subtitles": False,
        "audio_ui": False,
        "source": "qiaomu-mtv-creator classic",
    }
    timeline = {
        "duration_ms": duration_ms,
        "scenes": [
            {
                "id": f"scene_{scene['index']:02d}",
                "start_ms": scene["start_ms"],
                "end_ms": scene["end_ms"],
                "text": scene["text"],
            }
            for scene in scenes
        ],
    }
    (out_dir / "visual_config.json").write_text(
        json.dumps(visual, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cards = "\n".join(
        f"<article><h2>Scene {scene['index']}</h2><p>{scene['start_ms'] / 1000:.1f}s – {scene['end_ms'] / 1000:.1f}s</p>"
        f"<p>{_escape(scene['text'])}</p></article>"
        for scene in scenes
    )
    (out_dir / "storyboard.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>MTV storyboard</title>"
        f"<h1>{_escape(title)}</h1><p>{_escape(artist)} · {profile}</p>{cards}\n",
        encoding="utf-8",
    )
    return visual


def hero_fragment(text: str, *, kind: str = "lyric") -> str:
    """Short run for giant background type. Long captions look like leftover subtitles."""
    raw = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not raw:
        return ""
    latin = bool(re.search(r"[A-Za-z]", raw)) and not re.search(
        r"[\u3040-\u30ff\u3400-\u9fff]", raw
    )
    if kind == "title" or latin:
        return raw.split()[0][:12]
    compact = re.sub(r"[\s/·]+", "", raw)
    chunk = re.match(r"[\u3400-\u9fff々]{1,3}[\u3040-\u309f]{0,3}", compact)
    if chunk and len(chunk.group(0)) >= 2:
        return chunk.group(0)[:4]
    return compact[:4]


def overflow_anchor(
    width: int, height: int, layout: int, count: int = 4
) -> tuple[int, int]:
    """Park giant type so about half a glyph hangs off one edge."""
    step = max(width / max(count, 1), 1)
    if layout % 4 == 0:
        return (-int(step * 0.42), int(HEIGHT * 0.36))
    if layout % 4 == 1:
        return (WIDTH - width + int(step * 0.42), int(HEIGHT * 0.26))
    if layout % 4 == 2:
        return (int((WIDTH - width) / 2), HEIGHT - int(height * 0.78))
    return (-int(step * 0.28), HEIGHT - int(height * 0.82))


def _text_box(text: str, font) -> tuple[int, int, int, int]:
    from PIL import Image, ImageDraw

    probe = Image.new("RGB", (8, 8))
    box = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
    return box


def render_scene_image(
    path: Path,
    color_a: str,
    color_b: str,
    seed: int,
    headline: str = "",
    kicker: str = "",
    kind: str = "lyric",
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError as exc:
        raise RuntimeError("需要 Pillow 才能绘制 MTV 分镜海报") from exc

    r0, g0, b0 = _hex_rgb(color_a)
    r1, g1, b1 = _hex_rgb(color_b)
    image = Image.new("RGB", (WIDTH, HEIGHT), color_a)
    pixels = image.load()
    for y in range(0, HEIGHT, 2):
        ty = y / HEIGHT
        for x in range(0, WIDTH, 2):
            tx = x / WIDTH
            wave = 0.12 * math.sin((x / 70) + seed) + 0.08 * math.cos((y / 90) - seed)
            t = min(1.0, max(0.0, tx * 0.55 + ty * 0.45 + wave))
            rgb = (
                int(r0 + (r1 - r0) * t),
                int(g0 + (g1 - g0) * t),
                int(b0 + (b1 - b0) * t),
            )
            pixels[x, y] = rgb
            if x + 1 < WIDTH:
                pixels[x + 1, y] = rgb
            if y + 1 < HEIGHT:
                pixels[x, y + 1] = rgb
                if x + 1 < WIDTH:
                    pixels[x + 1, y + 1] = rgb
    image = image.filter(ImageFilter.GaussianBlur(radius=1.2))
    draw = ImageDraw.Draw(image, "RGBA")
    motif = seed % 4
    if motif == 0:
        draw.rectangle((0, HEIGHT - 280, 18, HEIGHT), fill=(245, 193, 108, 210))
        draw.ellipse(
            (WIDTH - 520, -180, WIDTH + 80, 420), outline=(255, 255, 255, 40), width=10
        )
    elif motif == 1:
        draw.rectangle((WIDTH - 28, 0, WIDTH, HEIGHT), fill=(255, 77, 141, 160))
        draw.line((120, 180, WIDTH - 160, 220), fill=(255, 255, 255, 50), width=6)
    elif motif == 2:
        draw.ellipse((80, 120, 420, 460), outline=(245, 193, 108, 70), width=8)
        draw.rectangle(
            (80, HEIGHT - 160, WIDTH - 80, HEIGHT - 148), fill=(255, 255, 255, 45)
        )
    else:
        draw.polygon([(0, 0), (420, 0), (0, 280)], fill=(255, 255, 255, 18))
        draw.rectangle((0, 0, WIDTH, 16), fill=(245, 193, 108, 150))

    font_path = _scene_font()
    headline = (headline or "").strip()
    kicker = (kicker or "").strip()
    layout = seed % 4
    image = image.convert("RGBA")
    type_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    type_draw = ImageDraw.Draw(type_layer)
    if kind == "title":
        title_font = (
            ImageFont.truetype(font_path, 120)
            if font_path
            else ImageFont.load_default()
        )
        kick_font = ImageFont.truetype(font_path, 36) if font_path else title_font
        if kicker:
            type_draw.text((96, 318), kicker, font=kick_font, fill=(255, 255, 255, 200))
        if headline:
            type_draw.text(
                (90, 372), headline, font=title_font, fill=(255, 255, 255, 245)
            )
    elif headline:
        fragment = hero_fragment(headline, kind=kind)
        size = 300 if not re.search(r"[A-Za-z]", fragment) else 240
        hero_font = (
            ImageFont.truetype(font_path, size)
            if font_path
            else ImageFont.load_default()
        )
        box = _text_box(fragment, hero_font)
        tw, th = box[2] - box[0], box[3] - box[1]
        x, y = overflow_anchor(tw, th, layout, count=max(len(fragment), 1))
        type_draw.text(
            (x - box[0], y - box[1]),
            fragment,
            font=hero_font,
            fill=(255, 255, 255, 118),
        )
    image = Image.alpha_composite(image, type_layer).convert("RGB")
    overlay = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    image = Image.blend(image, overlay, 0.10)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")


def compose_mtv(
    out_dir: Path,
    *,
    audio_path: Path,
    title: str,
    artist: str = "",
    timeline: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    cover_path: Path | None = None,
) -> dict[str, Any]:
    """Write mtv.mp4 plus storyboard artifacts. Does not burn lyrics."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("需要 ffmpeg 才能合成 MTV")
    if not audio_path.exists():
        raise RuntimeError("没有可合成 MTV 的音频")

    cues = list((timeline or {}).get("cues") or [])
    duration_ms = duration_ms or _audio_duration_ms(audio_path)
    lyrics = " ".join(str(cue.get("text") or "") for cue in cues)
    profile = pick_profile(title, lyrics)
    scenes = group_scenes(cues, duration_ms)
    write_project_files(
        out_dir,
        title=title,
        artist=artist,
        profile=profile,
        scenes=scenes,
        duration_ms=duration_ms,
    )

    images_dir = out_dir / "mtv-scenes"
    images_dir.mkdir(parents=True, exist_ok=True)
    colors = PROFILES[profile]["colors"]
    image_paths: list[Path] = []
    if cover_path and cover_path.exists():
        dest = images_dir / "scene_00.png"
        _cover_still(cover_path, dest)
        image_paths.append(dest)
        if scenes:
            scenes[0]["image"] = dest.name
    start_index = 1 if image_paths and len(scenes) > 1 else 0
    for offset, scene in enumerate(scenes[start_index:] or scenes):
        if scene.get("image") and (images_dir / scene["image"]).exists():
            continue
        color_a, color_b = colors[offset % len(colors)]
        dest = images_dir / f"scene_{scene['index']:02d}.png"
        headline = (
            title
            if scene.get("kind") == "title"
            else (scene.get("lines") or [scene.get("text") or ""])[0]
        )
        kicker = artist if scene.get("kind") == "title" else title
        render_scene_image(
            dest,
            color_a,
            color_b,
            seed=scene["index"] + offset,
            headline=headline,
            kicker=kicker[:24],
            kind=str(scene.get("kind") or "lyric"),
        )
        image_paths.append(dest)
        scene["image"] = dest.name

    if not image_paths:
        raise RuntimeError("没有 MTV 分镜图")

    timings = _scene_timings(scenes, duration_ms, len(image_paths))
    output = out_dir / "mtv.mp4"
    _xfade_compose(
        image_paths, timings, output, profile=profile, duration_ms=duration_ms
    )
    write_project_files(
        out_dir,
        title=title,
        artist=artist,
        profile=profile,
        scenes=scenes,
        duration_ms=duration_ms,
    )
    return {
        "file": "mtv.mp4",
        "profile": profile,
        "scenes": len(image_paths),
        "burn_subtitles": False,
    }


def _scene_timings(
    scenes: list[dict[str, Any]], duration_ms: int, count: int
) -> list[dict[str, float]]:
    if scenes and len(scenes) == count:
        rows = []
        for scene in scenes:
            start = scene["start_ms"] / 1000
            duration = max((scene["end_ms"] - scene["start_ms"]) / 1000, 1.2)
            rows.append({"start": start, "duration": duration})
        return rows
    each = max((duration_ms / 1000) / max(count, 1), 1.2)
    return [{"start": index * each, "duration": each} for index in range(count)]


def _xfade_compose(
    images: list[Path],
    timings: list[dict[str, float]],
    output: Path,
    profile: str = "cinematic",
    duration_ms: int = 0,
) -> None:
    fade = 0.7
    if timings:
        fade = min(fade, max(0.12, min(item["duration"] for item in timings) / 3))
    styles = TRANSITIONS.get(profile, TRANSITIONS["cinematic"])
    inputs: list[str] = []
    for index, image in enumerate(images):
        extra = fade if index < len(images) - 1 else 0
        inputs.extend(
            [
                "-loop",
                "1",
                "-t",
                f"{timings[index]['duration'] + extra:.3f}",
                "-i",
                str(image),
            ]
        )
    filters = []
    for index in range(len(images)):
        crop_x = 16 + (index * 17) % 28
        crop_y = 10 + (index * 13) % 20
        filters.append(
            f"[{index}:v]scale={WIDTH + 48}:{HEIGHT + 32},"
            f"crop={WIDTH}:{HEIGHT}:{crop_x}:{crop_y},setsar=1,fps=24[v{index}]"
        )
    if len(images) == 1:
        filters.append("[v0]copy[vout]")
    else:
        cumulative = timings[0]["duration"]
        label = "vout" if len(images) == 2 else "vt1"
        first_tr = styles[0]
        filters.append(
            f"[v0][v1]xfade=transition={first_tr}:duration={fade:.3f}:offset={cumulative:.3f}[{label}]"
        )
        for index in range(2, len(images)):
            cumulative += timings[index - 1]["duration"]
            out = "vout" if index == len(images) - 1 else f"vt{index}"
            prev = "vt1" if index == 2 else f"vt{index - 1}"
            trans = styles[(index - 1) % len(styles)]
            filters.append(
                f"[{prev}][v{index}]xfade=transition={trans}:duration={fade:.3f}:offset={cumulative:.3f}[{out}]"
            )

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-an",
        "-t",
        f"{max(duration_ms, 1000) / 1000:.3f}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "26",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=600, check=False)
    if result.returncode != 0 or not output.exists():
        _concat_fallback(images, timings, output, duration_ms)


def _concat_fallback(
    images: list[Path], timings: list[dict[str, float]], output: Path, duration_ms: int
) -> None:
    parts: list[str] = []
    for index, image in enumerate(images):
        parts.extend(
            ["-loop", "1", "-t", f"{timings[index]['duration']:.3f}", "-i", str(image)]
        )
    concat = "".join(
        f"[{index}:v]scale={WIDTH}:{HEIGHT},setsar=1,fps=24[v{index}];"
        for index in range(len(images))
    )
    concat += (
        "".join(f"[v{index}]" for index in range(len(images)))
        + f"concat=n={len(images)}:v=1:a=0[vout]"
    )
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            *parts,
            "-filter_complex",
            concat,
            "-map",
            "[vout]",
            "-an",
            "-t",
            f"{max(duration_ms, 1000) / 1000:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            str(output),
        ],
        capture_output=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0 or not output.exists():
        err = (result.stderr or b"").decode("utf-8", "ignore")[-400:]
        raise RuntimeError(f"FFmpeg 合成 MTV 失败：{err}")


def _cover_still(src: Path, dest: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
            "-frames:v",
            "1",
            str(dest),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )


def _audio_duration_ms(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    try:
        return max(1000, int(float((result.stdout or "0").strip()) * 1000))
    except ValueError:
        return 60_000


def _scene_font() -> str:
    for candidate in (
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).exists():
            return candidate
    return ""


def _drawtext(font: str, text: str, x: str, y: str, size: int, color: str) -> str:
    cleaned = (
        re.sub(r"[\r\n]+", " ", text)
        .replace("\\", "")
        .replace("'", "")
        .replace(":", " ")
    )
    font_esc = font.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return (
        f"drawtext=fontfile='{font_esc}':text='{cleaned}':x={x}:y={y}:"
        f"fontsize={size}:fontcolor={color}:shadowcolor=black@0.55:shadowx=3:shadowy=3"
    )


def _hex_rgb(color: str) -> tuple[int, int, int]:
    raw = color.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
