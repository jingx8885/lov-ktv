import json

import pytest

from lovktv.agents import translate
from lovktv.agents.ja_lyrics import (
    apply_ja_annotation,
    restore_romaji_unit,
    romaji_to_hiragana,
)
from lovktv.agents.translate import apply_zh_translation, translate_lines
from lovktv.workers import lyric_audit
from lovktv.workers.lyric_audit import audit_timeline, repair_song


def _cue(text, zh="", tokens=None, start=0, end=1000):
    cue = {"text": text, "start_ms": start, "end_ms": end}
    if zh:
        cue["zh"] = zh
        cue["translation"] = zh
    cue["tokens"] = tokens or [
        {"text": text, "start_ms": start, "end_ms": end, "reading": ""}
    ]
    return cue


def test_romaji_to_hiragana_converts_japanese_only():
    assert romaji_to_hiragana("dakedo") == "だけど"
    assert romaji_to_hiragana("shimbun") == "しんぶん"
    assert romaji_to_hiragana("matcha") == "まっちゃ"
    assert romaji_to_hiragana("kyou") == "きょう"
    assert romaji_to_hiragana("love") == ""
    assert romaji_to_hiragana("only") == ""
    assert romaji_to_hiragana("it's") == ""


def test_restore_romaji_unit_moves_reading_into_surface():
    unit = {
        "sing": "iribitatta",
        "surface": "iribitatta",
        "label": "いりびたった",
        "reading": "いりびたった",
        "romaji": "iribitatta",
        "zh": "突然闯入",
    }
    fixed = restore_romaji_unit(unit)
    assert fixed["surface"] == "いりびたった"
    assert fixed["reading"] == ""
    assert fixed["romaji"] == "iribitatta"
    assert fixed["pronunciation"] == {"system": "romaji", "value": "iribitatta"}
    # kanji reading is left to pykakasi
    kanji = restore_romaji_unit({"surface": "tomatta", "reading": "止まった", "romaji": "tomatta"})
    assert kanji["surface"] == "止まった"
    # canonical units and English words are untouched
    assert restore_romaji_unit({"surface": "君", "reading": "きみ"})["surface"] == "君"
    english = {"surface": "love", "reading": "", "romaji": ""}
    assert restore_romaji_unit(english, source="It's only love") is english
    # a romaji particle with no Japanese at all becomes kana on a romaji line
    particle = restore_romaji_unit(
        {"surface": "wa", "reading": "", "romaji": "wa"}, source="nante koto wa nakattawa"
    )
    assert particle["surface"] == "は"
    # ... but never on a mixed line where it could be English
    mixed = {"surface": "me", "reading": "", "romaji": "me"}
    assert restore_romaji_unit(mixed, source="Stay with me 真夜中のドア") is mixed


def test_apply_annotation_restores_cached_romaji_surface_notes():
    timeline = {
        "language": "ja",
        "cues": [
            _cue("iribitatta chirakaru heya mo", zh="tuturu"),
            _cue("nante koto wa nakattawa"),
        ],
    }
    notes = {
        "model": "test",
        "lines": [
            {
                "source": "iribitatta chirakaru heya mo",
                "zh": "突然闯入、四散开来的房间也",
                "units": [
                    {"surface": "iribitatta", "reading": "いりびたった", "romaji": "iribitatta", "zh": "突然闯入"},
                    {"surface": "chirakaru", "reading": "ちらかる", "romaji": "chirakaru", "zh": "四散开来"},
                    {"surface": "heya", "reading": "部屋", "romaji": "heya", "zh": "room"},
                    {"surface": "mo", "reading": "も", "romaji": "mo", "zh": "也"},
                ],
            },
            {
                "source": "nante koto wa nakattawa",
                "zh": "nothing special happened",
                "units": [
                    {"surface": "なんて", "reading": "", "romaji": "nante", "zh": "什么"},
                    {"surface": "こと", "reading": "", "romaji": "koto", "zh": "事"},
                    {"surface": "wa", "reading": "", "romaji": "wa", "zh": ""},
                    {"surface": "なかったわ", "reading": "", "romaji": "nakattawa", "zh": "没有"},
                ],
            },
        ],
    }
    apply_ja_annotation(timeline, notes)
    first, second = timeline["cues"]
    assert first["text"] == "いりびたったちらかる部屋も"
    assert first["source_text"] == "iribitatta chirakaru heya mo"
    assert first["zh"] == "突然闯入、四散开来的房间也"
    by_text = {tok["text"]: tok for tok in first["tokens"]}
    assert by_text["いりびたった"]["romaji"] == "iribitatta"
    assert by_text["部屋"]["reading"] == "へや"
    assert by_text["部屋"].get("zh", "") == ""  # English gloss dropped
    assert second["text"] == "なんてことはなかったわ"
    assert "zh" not in second  # English line translation dropped, not copied
    assert audit_timeline(timeline)["romaji_cues"] == []


def test_audit_flags_romaji_and_english_translations():
    timeline = {
        "language": "ja",
        "cues": [
            _cue(
                "kanjin na koto ga",
                zh="重要的事",
                tokens=[
                    {"text": "kanjin", "romaji": "kanjin", "zh": "重要", "start_ms": 0, "end_ms": 500},
                    {"text": "na", "romaji": "na", "zh": "的", "start_ms": 500, "end_ms": 1000},
                ],
            ),
            _cue("IT'S ONLY LOVE", zh="It's only love"),
            _cue(
                "コーヒーのしみ",
                zh="咖啡的污渍",
                tokens=[{"text": "コーヒー", "zh": "coffee", "start_ms": 0, "end_ms": 1000}],
            ),
            _cue("So La Si Si La"),
        ],
    }
    report = audit_timeline(timeline)
    assert report["romaji_cues"] == ["kanjin na koto ga"]
    assert report["bad_line_zh"] == [{"text": "IT'S ONLY LOVE", "zh": "It's only love"}]
    assert report["bad_token_zh"][0]["zh"] == "coffee"
    assert report["missing_line_zh"] == []
    assert report["ok"] is False
    clean = {
        "language": "en",
        "cues": [_cue("Stay with me", zh="留在我身边"), _cue("Oh oh")],
    }
    assert audit_timeline(clean)["ok"] is True


def test_audit_flags_romaji_cue_with_japanese_tokens():
    timeline = {
        "language": "ja",
        "cues": [
            _cue(
                "sugiru hibi ni",
                zh="流逝的日子里",
                tokens=[
                    {"text": "過ぎる", "surface": "過ぎる", "reading": "すぎる"},
                    {"text": "日々", "surface": "日々", "reading": "ひび"},
                ],
            )
        ],
    }
    assert audit_timeline(timeline)["romaji_cues"] == ["sugiru hibi ni"]


def test_apply_annotation_replaces_legacy_confusable_romaji_surface():
    timeline = {
        "language": "ja",
        "cues": [
            _cue(
                "egaitе kita",
                tokens=[
                    {"text": "描いて", "surface": "描いて", "reading": "えがいて", "romaji": "egaite"},
                    {"text": "きた", "surface": "きた", "reading": "", "romaji": "kita"},
                ],
            )
        ],
    }
    notes = {
        "lines": [
            {
                "source": "egaitе kita",
                "units": [
                    {"surface": "描いて", "reading": "えがいて", "romaji": "egaite"},
                    {"surface": "きた", "reading": "", "romaji": "kita"},
                ],
            }
        ]
    }
    apply_ja_annotation(timeline, notes)
    assert timeline["cues"][0]["text"] == "描いてきた"


def test_apply_zh_translation_replaces_english_line_without_overwrite():
    timeline = {
        "language": "en",
        "cues": [
            _cue(
                "I miss you",
                zh="I miss you",
                tokens=[
                    {"text": "I", "zh": "I", "start_ms": 0, "end_ms": 300},
                    {"text": "miss", "zh": "", "start_ms": 300, "end_ms": 600},
                    {"text": "you", "start_ms": 600, "end_ms": 1000},
                ],
            )
        ],
    }
    notes = {
        "model": "test",
        "lines": [
            {
                "source": "I miss you",
                "translation": "我想念你",
                "units": [
                    {"surface": "I", "translation": "我"},
                    {"surface": "miss", "translation": "miss"},
                    {"surface": "you", "translation": "你"},
                ],
            }
        ],
    }
    apply_zh_translation(timeline, notes)
    cue = timeline["cues"][0]
    assert cue["zh"] == "我想念你"
    glosses = [tok.get("zh", "") for tok in cue["tokens"]]
    assert glosses[0] == "我" and glosses[2] == "你"
    assert glosses[1] == ""  # the English gloss is never written back


def test_translate_lines_retries_lines_not_answered_in_chinese(tmp_path, monkeypatch):
    calls = []

    def fake_complete(messages):
        user = messages[-1]["content"]
        calls.append(user)
        if len(calls) == 1:
            return {
                "lines": [
                    {"source": "I miss you", "translation": "I miss you", "units": []},
                    {"source": "Hold on", "translation": "坚持住", "units": []},
                ]
            }
        return {"lines": [{"source": "I miss you", "translation": "我想念你", "units": []}]}

    monkeypatch.setattr(translate, "agent_enabled", lambda: True)
    monkeypatch.setattr(translate, "agent_model", lambda: "test")
    monkeypatch.setattr(translate, "complete_json", fake_complete)
    cache = tmp_path / "zh-translate.json"
    notes = translate_lines(["I miss you", "Hold on"], "t", "a", "en", cache_path=cache)
    assert [item["translation"] for item in notes["lines"]] == ["我想念你", "坚持住"]
    assert len(calls) == 2
    assert "I miss you" in calls[1] and "Hold on" not in calls[1]
    assert "not Chinese" in calls[1]

    # an old cache with English answers is repaired line by line, not thrown away
    cached = json.loads(cache.read_text(encoding="utf-8"))
    cached["lines"][1]["translation"] = "Hold on"
    cache.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
    calls.clear()

    def fake_repair(messages):
        calls.append(messages[-1]["content"])
        return {"lines": [{"source": "Hold on", "translation": "坚持住", "units": []}]}

    monkeypatch.setattr(translate, "complete_json", fake_repair)
    again = translate_lines(["I miss you", "Hold on"], "t", "a", "en", cache_path=cache)
    assert [item["translation"] for item in again["lines"]] == ["我想念你", "坚持住"]
    assert len(calls) == 1 and "I miss you" not in calls[0]
    assert json.loads(cache.read_text(encoding="utf-8"))["lines"][1]["translation"] == "坚持住"


def test_translate_lines_retries_transient_agent_failure(tmp_path, monkeypatch):
    calls = 0

    def flaky_complete(_messages):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary gateway failure")
        return {"lines": [{"source": "I miss you", "translation": "我想念你", "units": []}]}

    monkeypatch.setenv("LOVKTV_TRANSLATION_RETRY_DELAY", "0")
    monkeypatch.setattr(translate, "agent_enabled", lambda: True)
    monkeypatch.setattr(translate, "agent_model", lambda: "test")
    monkeypatch.setattr(translate, "complete_json", flaky_complete)
    notes = translate_lines(["I miss you"], "t", "a", "en", cache_path=tmp_path / "zh.json")
    assert notes["lines"][0]["translation"] == "我想念你"
    assert calls == 2


def test_translate_lines_raises_after_exhausting_invalid_retries(tmp_path, monkeypatch):
    calls = 0

    def always_invalid(_messages):
        nonlocal calls
        calls += 1
        return {"lines": [{"source": "I miss you", "translation": "I miss you", "units": []}]}

    monkeypatch.setenv("LOVKTV_TRANSLATION_RETRY_DELAY", "0")
    monkeypatch.setattr(translate, "agent_enabled", lambda: True)
    monkeypatch.setattr(translate, "agent_model", lambda: "test")
    monkeypatch.setattr(translate, "complete_json", always_invalid)
    with pytest.raises(RuntimeError, match="重试后仍未返回有效中文"):
        translate_lines(["I miss you"], "t", "a", "en", cache_path=tmp_path / "zh.json")
    assert calls == 3


def test_repair_song_restores_romaji_from_cache_and_republishes(tmp_path, monkeypatch):
    song_dir = tmp_path / "s1"
    song_dir.mkdir()
    timeline = {
        "language": "ja",
        "alignment": "mugen",
        "cues": [
            _cue(
                "hajimete no Louvre wa",
                zh="第一次的卢浮宫啊",
                tokens=[  # real files also carry ``surface``; see normalize_timeline

                    {"text": "hajimete", "romaji": "hajimete", "zh": "第一次", "start_ms": 0, "end_ms": 400},
                    {"text": "no", "romaji": "no", "start_ms": 400, "end_ms": 500},
                    {"text": "Louvre", "reading": "Louvre", "start_ms": 500, "end_ms": 800},
                    {"text": "wa", "romaji": "wa", "start_ms": 800, "end_ms": 1000},
                ],
            )
        ],
    }
    timeline["cues"][0]["surface"] = "hajimete no Louvre wa"
    (song_dir / "lyrics.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    notes = {
        "model": "test",
        "lines": [
            {
                "source": "hajimete no Louvre wa",
                "zh": "第一次的卢浮宫啊",
                "units": [
                    {"surface": "hajimete", "reading": "はじめて", "romaji": "hajimete", "zh": "第一次"},
                    {"surface": "no", "reading": "", "romaji": "no", "zh": ""},
                    {"surface": "ルーヴル", "reading": "Louvre", "romaji": "", "zh": "卢浮宫"},
                    {"surface": "wa", "reading": "", "romaji": "wa", "zh": ""},
                ],
            }
        ],
    }
    (song_dir / "ja-annotate.json").write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")
    songs = {"s1": {"id": "s1", "title": "One Last Kiss", "artist": "Utada", "error": "x 注音降级：boom"}}
    monkeypatch.setattr(lyric_audit, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(lyric_audit, "get_song", lambda sid: songs.get(sid))
    monkeypatch.setattr(lyric_audit, "update_song", lambda sid, **f: songs[sid].update(f))
    monkeypatch.setattr(lyric_audit, "annotate_ja_lines", lambda *a, **k: (_ for _ in ()).throw(AssertionError("agent must not be called")))
    published = []
    import lovktv.media.oss as oss

    monkeypatch.setattr(oss, "publish_song", lambda sid: published.append(sid) or ["lyrics.json"])
    import lovktv.workers.restore_ja as restore_ja

    monkeypatch.setattr(restore_ja, "pack_timeline_to_voice", lambda *a, **k: False)

    assert lyric_audit.audit_song("s1")["romaji_cues"] == ["hajimete no Louvre wa"]
    result = repair_song("s1")
    assert result["ok"] is True
    assert result["actions"] == ["reapplied"]
    assert published == ["s1"]
    saved = json.loads((song_dir / "lyrics.json").read_text(encoding="utf-8"))
    cue = saved["cues"][0]
    assert cue["text"] == "はじめてのルーヴルは"
    assert cue["source_text"] == "hajimete no Louvre wa"
    assert cue["zh"] == "第一次的卢浮宫啊"
    assert songs["s1"]["error"] == ""
    # second run is a no-op
    assert repair_song("s1")["changed"] is False
