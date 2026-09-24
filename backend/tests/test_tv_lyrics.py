from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_tv_lyrics_use_readable_fixed_type():
    shared = (ROOT / "shared" / "lyrics" / "css" / "lyrics.css").read_text(
        encoding="utf-8"
    )
    tv = (ROOT / "tv" / "lyrics" / "css" / "lyrics.css").read_text(encoding="utf-8")
    stage = (ROOT / "tv" / "stage" / "css" / "stage.css").read_text(encoding="utf-8")
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "clamp(28px, 4.6vw, 58px)" in shared
    assert "font-size: 0.34em" in shared
    assert "font-size: .62em" in shared
    assert "--tv-lyric-scale: 1" in tv
    assert "clamp(36px, 3.4vw, 68px)" in tv
    assert "font-size: calc(clamp(36px, 3.4vw, 68px) * var(--tv-lyric-scale))" in tv
    assert "lyric-left" in tv
    assert "lyric-right" in tv
    assert "font-size: 42px" not in tv
    assert "clamp(18px, 2.8vw, 34px)" not in tv
    assert "position: absolute" in stage
    assert "bottom: 28px" in stage
    assert "body.tv .lyrics .anno .rt" in tv
    assert "body.tv .lyrics .anno .roma" in tv
    assert "body.tv .lyrics .anno .gloss" in tv
    assert "font-size: 0.5em" in tv
    assert "font-size: inherit" in tv
    assert "font-size: 0.42em" in tv
    assert "font-size: 0.52em" in tv
    assert "font-size: 0.36em" not in tv
    assert "font-size: .28em" not in tv
    assert "font-size: .62em" not in tv
    assert "backdrop-filter" not in tv
    assert "drop-shadow" not in tv
    assert 'href="/tv/lyrics/css/lyrics.css"' in html
    assert 'href="/shared/lyrics/css/lyrics.css"' in html
    assert 'id="lyricLeft"' in html
    assert 'id="lyricRight"' in html
    assert 'id="tvLyricSize"' in html
    assert 'class="line lyric-left is-wait"' in html
    assert 'class="line lyric-right is-wait"' in html
    assert 'id="prev"' not in html
    assert 'id="cur"' not in html
    assert 'class="tv is-waiting"' in html
    assert 'src="/brand/wait-tv.jpg"' in html
    assert 'id="appQrBox"' in html
    assert 'id="appQr"' in html
    assert 'href="/apps/phone.apk"' in html
    assert "wait-app-qr" in html
    assert "body.tv:not(.is-waiting) .wait-app-qr" in stage
    login = (ROOT / "tv" / "auth" / "js" / "login.js").read_text(encoding="utf-8")
    assert "export async function paintPhoneAppQr" in login
    assert 'fetchJson("/api/apps")' in login
    assert 'renderQr(href, "appQr")' in login
    assert "body.tv.is-waiting .lyric-plate" in tv
    assert "body.tv.is-waiting .lyric-plate" in shared
    assert "body.tv.is-waiting .wait-art" in stage
    assert 'href="/tv/stage/css/stage.css"' in html
    assert "min-height: 0.5em" in tv
    assert "min-height: 0.7em" in tv
    paint = (ROOT / "shared" / "lyrics" / "js" / "paint.js").read_text(encoding="utf-8")
    assert "function tvStage()" in paint
    assert "if (tvStage()) return;" in paint
    assert "function fitTvLyricLine" in paint
    assert 'const keepGloss = showExtra && script !== "zh"' in paint
    assert "function tokenGapHtml" in paint
    assert "align-items: flex-start" in shared
    assert 'body[data-lyric-script="zh"] .line' in shared
    assert "column-gap: 0" in shared
    assert ".lyrics .anno .gloss:empty::before" in shared
    assert "transform: none !important" in tv
    assert "export function sanitizeLyrics" in paint
    tick = (ROOT / "tv" / "playback" / "js" / "runtime" / "tick.js").read_text(
        encoding="utf-8"
    )
    assert "sanitizeLyrics(lyricsHit.data)" in tick
    assert "const next = sanitizeLyrics(data)" in tick
    paint_tv = (ROOT / "tv" / "playback" / "js" / "lyric" / "paint.js").read_text(
        encoding="utf-8"
    )
    karaoke = (ROOT / "tv" / "playback" / "js" / "lyric" / "karaoke.js").read_text(
        encoding="utf-8"
    )
    size = (ROOT / "tv" / "playback" / "js" / "lyric" / "size.js").read_text(
        encoding="utf-8"
    )
    remote = (ROOT / "tv" / "playback" / "js" / "remote" / "controls.js").read_text(
        encoding="utf-8"
    )
    assert "export function karaokePair" in karaoke
    assert "even cues sit on the left" in karaoke
    assert "from \"./karaoke.js\"" in paint_tv
    assert "paintKaraokeLine($(\"lyricLeft\")" in paint_tv
    assert "paintKaraokeLine($(\"lyricRight\")" in paint_tv
    assert "export function applyLyricSize" in size
    assert "export const LYRIC_SIZE_MIN = 70" in size
    assert "export const LYRIC_SIZE_MAX = 250" in size
    assert "export const LYRIC_SIZE_STEP = 10" in size
    assert "data-lyric-size" not in tv
    assert 'words.style.flexWrap = "wrap"' in paint
    assert "applyLyricSize()" in remote
    assert "nudgeFocusedSetting(-1)" in remote
    assert "nudgeFocusedSetting(1)" in remote
    assert 'id="tvLyricSize"' in html
    assert ".tv.has-native-mv .lyrics .prev" not in stage


def test_tv_karaoke_pair_keeps_even_left_odd_right():
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node，才能跑卡拉 OK 两行配对")
    script = r"""
import { karaokePair } from './frontend/public/tv/playback/js/lyric/karaoke.js';
const cues = [0, 1, 2, 3, 4].map((i) => ({
  start_ms: i * 1000,
  end_ms: i * 1000 + 800,
  text: String(i)
}));
function check(t, left, right, live) {
  const pair = karaokePair(cues, t);
  const gotLeft = pair.left && pair.left.text;
  const gotRight = pair.right && pair.right.text;
  if (gotLeft !== left || gotRight !== right || pair.liveIndex !== live) {
    throw new Error(`t=${t} got ${gotLeft}/${gotRight}/${pair.liveIndex} want ${left}/${right}/${live}`);
  }
  if (live >= 0 && live % 2 === 0 && pair.leftTime < 0) throw new Error("even live should fill left");
  if (live >= 0 && live % 2 === 1 && pair.rightTime < 0) throw new Error("odd live should fill right");
}
check(100, "0", "1", 0);
check(900, "0", "1", -1);
check(1100, "2", "1", 1);
check(2100, "2", "3", 2);
check(4100, "4", "3", 4);
check(5000, "4", "3", -1);
const empty = karaokePair([], 0);
if (empty.left || empty.right || empty.liveIndex !== -1) throw new Error("empty cues");
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT.parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_zh_lyrics_skip_per_char_gaps_and_keep_empty_gloss_rows():
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node，才能跑歌词 token 空隙")
    script = r"""
globalThis.document = {
  body: {
    dataset: { lyricScript: "zh" },
    classList: { contains: () => false }
  }
};
const { renderCue } = await import("./frontend/public/shared/lyrics/js/paint.js");
const zhCue = {
  text: "晴天 My way",
  translation: "晴天",
  tokens: [
    { text: "晴", surface: "晴", start_ms: 0, end_ms: 200 },
    { text: "天", surface: "天", start_ms: 200, end_ms: 400 },
    { text: "My", surface: "My", start_ms: 400, end_ms: 600 },
    { text: "way", surface: "way", start_ms: 600, end_ms: 800 }
  ]
};
const zhHtml = renderCue(zhCue, 0, "all");
if (zhHtml.includes('class="gloss"')) throw new Error("zh should not keep per-token gloss");
if (zhHtml.includes("tok-space") && !zhHtml.includes("</span><span class=\"tok-space\"> </span><span class=\"tok latin\"")) {
  throw new Error("zh tok-space should only sit at the CJK/Latin boundary");
}
if ((zhHtml.match(/tok-space/g) || []).length !== 2) {
  throw new Error("zh wants one CJK/Latin gap plus one Latin/Latin gap, got " + zhHtml);
}
const betweenHan = zhHtml.split("class=\"tok\"")[1];
if (betweenHan.includes("tok-space")) throw new Error("Han characters must not have tok-space: " + zhHtml);

document.body.dataset.lyricScript = "ja";
const jaCue = {
  text: "世界",
  tokens: [
    { text: "世界", surface: "世界", translation: "世界", start_ms: 0, end_ms: 400 },
    { text: "へ", surface: "へ", start_ms: 400, end_ms: 600 }
  ]
};
const jaHtml = renderCue(jaCue, 0, "all");
if ((jaHtml.match(/class="gloss"/g) || []).length !== 2) {
  throw new Error("ja must keep empty gloss so the source row stays aligned: " + jaHtml);
}
if (!jaHtml.includes('<span class="gloss"></span>')) {
  throw new Error("untranslated ja token must still emit empty gloss: " + jaHtml);
}
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT.parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_tv_page_has_no_language_picker():
    html = (ROOT / "tv.html").read_text(encoding="utf-8")
    assert "lang-picker" not in html
    assert "data-set-lang" not in html
