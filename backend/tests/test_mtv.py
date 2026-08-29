from lovktv.pipeline.mtv import (
    HEIGHT,
    WIDTH,
    group_scenes,
    hero_fragment,
    overflow_anchor,
    pick_profile,
    render_scene_image,
    write_project_files,
)


def test_pick_profile_from_lyrics():
    assert pick_profile("夜", "玻璃上的雨") == "dream"
    assert pick_profile("信号", "霓虹赛博") == "glitch"
    assert pick_profile("晴天", "我爱你") == "poster"
    assert pick_profile("Untitled", "x") == "minimal"
    assert (
        pick_profile(
            "群青", "過ぎる日々にあくびが出る 本当の自分に出会えた 群青の世界へ"
        )
        == "cinematic"
    )


def test_group_scenes_respects_bounds_and_cap():
    cues = [
        {"text": f"line{i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
        for i in range(20)
    ]
    scenes = group_scenes(
        cues, duration_ms=20_000, min_ms=3500, max_ms=8000, max_scenes=6
    )
    assert 1 <= len(scenes) <= 6
    for scene in scenes:
        assert scene["end_ms"] > scene["start_ms"]
    assert scenes[0]["start_ms"] == 0
    assert scenes[-1]["end_ms"] >= 20_000


def test_group_scenes_breaks_on_instrumental_gap():
    cues = [
        {"text": "intro a", "start_ms": 1050, "end_ms": 4710},
        {"text": "intro b", "start_ms": 4710, "end_ms": 9180},
        {"text": "verse", "start_ms": 25060, "end_ms": 29000},
    ]
    scenes = group_scenes(
        cues, duration_ms=30_000, min_ms=3500, max_ms=8000, max_scenes=8
    )
    assert scenes[0]["kind"] == "title"
    singing = [scene for scene in scenes if scene.get("kind") != "title"]
    assert singing[0]["end_ms"] <= 10000
    assert singing[1]["start_ms"] >= 24000


def test_visual_config_does_not_burn_subtitles(tmp_path):
    scenes = [
        {"index": 1, "start_ms": 0, "end_ms": 4000, "text": "hello", "lines": ["hello"]}
    ]
    visual = write_project_files(
        tmp_path,
        title="Salt On Glass",
        artist="测试歌手",
        profile="cinematic",
        scenes=scenes,
        duration_ms=4000,
    )
    assert visual["burn_subtitles"] is False
    assert visual["audio_ui"] is False
    assert (tmp_path / "visual_config.json").exists()
    assert (tmp_path / "timeline.json").exists()
    assert "Salt On Glass" in (tmp_path / "storyboard.html").read_text(encoding="utf-8")


def test_hero_fragment_is_short_poster_type():
    assert hero_fragment("どうでもいいような夜だけど") == "どうでも"
    assert hero_fragment("乱れた部屋に 掠れたメロディ") == "乱れた"
    assert hero_fragment("溢れるメモリー") == "溢れる"
    assert hero_fragment("NIGHT DANCER", kind="title") == "NIGHT"
    assert hero_fragment("") == ""


def test_overflow_anchor_hangs_off_the_frame():
    x, y = overflow_anchor(1200, 300, 0, count=4)
    assert x < 0
    x, y = overflow_anchor(1200, 300, 1, count=4)
    assert x + 1200 > WIDTH
    x, y = overflow_anchor(1200, 400, 2, count=4)
    assert y + 400 > HEIGHT


def test_lyric_scene_draws_giant_type_to_the_edge(tmp_path):
    dest = tmp_path / "scene.png"
    render_scene_image(
        dest,
        "#0b1020",
        "#2a1848",
        seed=0,
        headline="どうでもいいような夜だけど",
        kind="lyric",
    )
    from PIL import Image

    image = Image.open(dest)
    assert image.size == (WIDTH, HEIGHT)
    edge = [image.getpixel((0, y)) for y in range(0, HEIGHT, 8)]
    assert any(sum(pixel) > 80 for pixel in edge)
