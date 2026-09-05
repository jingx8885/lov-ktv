"""Build a Duolingo-style campaign from one song's lyrics."""

from __future__ import annotations

import json
from typing import Any

from lovktv.locale.i18n import translate
from lovktv.storage import learn as learn_store
from lovktv.workers.learn import (
    _choices,
    _line_pools,
    _norm,
    _question,
    _seeded_rng,
    _song_meta,
    _unique,
    content_tokens,
    cue_romaji,
    cue_text,
    cue_zh,
    has_useful_zh,
    is_singable_cue,
    tap_words,
)

CAMPAIGN_SCHEMA = "lovktv-learn-campaign-v1"
LINES_PER_UNIT = 4
SKILLS = ("word", "sentence", "listen", "read", "sing")
PASS_PCT = 70
LESSON_SIZE = 8
REVIEW_SIZE = 12
MASTERY_STREAK = 2

_SKILL_PLAY = {"read": "tap", "sing": "echo"}


def _has_kanji(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in str(text or ""))


def singable_cues(
    timeline: dict[str, Any], song: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Lines worth learning: drops instrumental markers, credits/metadata,
    the title line and pure interjection lines ("ah~", "la la la")."""
    meta = _song_meta(timeline, song)
    return [
        cue
        for position, cue in enumerate(timeline.get("cues") or [])
        if isinstance(cue, dict) and is_singable_cue(cue, meta, position)
    ]


def line_record(cue: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "start_ms": int(cue.get("start_ms") or 0),
        "end_ms": int(cue.get("end_ms") or 0),
        "text": cue_text(cue),
        "zh": cue_zh(cue),
        "romaji": cue_romaji(cue),
        "words": tap_words(cue),
    }


def knowledge_words(cues: list[dict[str, Any]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for cue in cues:
        for token in content_tokens(cue, include_function=False):
            key = _norm(token["text"])
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "kind": "word",
                    "key": key,
                    "text": token["text"],
                    "zh": token["zh"],
                }
            )
    if found:
        return found
    for cue in cues:
        for token in content_tokens(cue, include_function=True):
            key = _norm(token["text"])
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "kind": "word",
                    "key": key,
                    "text": token["text"],
                    "zh": token["zh"],
                }
            )
    return found


def knowledge_sentences(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, cue in enumerate(cues):
        text = cue_text(cue)
        key = _norm(text)
        if not key or key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "kind": "sentence",
                "key": key,
                "text": text,
                "zh": cue_zh(cue),
                "index": index,
                "start_ms": int(cue.get("start_ms") or 0),
                "end_ms": int(cue.get("end_ms") or 0),
            }
        )
    return found


def chunk_units(cues: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not cues:
        return []
    chunks = [
        cues[index : index + LINES_PER_UNIT]
        for index in range(0, len(cues), LINES_PER_UNIT)
    ]
    if len(chunks) >= 2 and len(chunks[-1]) == 1:
        chunks[-2].extend(chunks.pop())
    return chunks


def unit_id_for(index: int) -> str:
    return f"u{index}"


def _progress_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(row["unit_id"], row["skill"]): row for row in rows}


def _mastered_set(rows: list[dict[str, Any]], kind: str) -> set[str]:
    return {
        str(row["item_key"])
        for row in rows
        if row.get("kind") == kind and int(row.get("mastered") or 0)
    }


def _passed(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("status") in {"passed", "mastered"})


def build_campaign(
    timeline: dict[str, Any],
    song: dict[str, Any] | None = None,
    *,
    progress: list[dict[str, Any]] | None = None,
    mastery: list[dict[str, Any]] | None = None,
    mistakes: int = 0,
    lang: str = "zh",
) -> dict[str, Any]:
    song = song or {}
    cues = singable_cues(timeline, song)
    lines = [line_record(cue, index) for index, cue in enumerate(cues)]
    words = knowledge_words(cues)
    sentences = knowledge_sentences(cues)
    units_raw = chunk_units(cues)
    saved = _progress_map(progress or [])
    mastered_words = _mastered_set(mastery or [], "word")
    mastered_sents = _mastered_set(mastery or [], "sentence")
    prev_unit_done = True
    units: list[dict[str, Any]] = []
    read_done = 0
    sing_done = 0
    for unit_index, chunk in enumerate(units_raw):
        uid = unit_id_for(unit_index)
        start = sum(len(part) for part in units_raw[:unit_index])
        end = start + len(chunk)
        skills: list[dict[str, Any]] = []
        prev_skill_ok = prev_unit_done
        unit_all_ok = True
        for skill in SKILLS:
            row = saved.get((uid, skill))
            if _passed(row):
                status = str(row.get("status") or "passed")
            elif prev_skill_ok:
                status = "ready"
            else:
                status = "locked"
            if status in {"passed", "mastered"}:
                prev_skill_ok = True
            else:
                prev_skill_ok = False
                unit_all_ok = False
            if skill == "read" and _passed(row):
                read_done += 1
            if skill == "sing" and _passed(row):
                sing_done += 1
            skills.append(
                {
                    "id": skill,
                    "status": status,
                    "score": int(row.get("score") or 0) if row else 0,
                    "attempts": int(row.get("attempts") or 0) if row else 0,
                    "play_mode": _SKILL_PLAY.get(skill),
                }
            )
        prev_unit_done = unit_all_ok
        units.append(
            {
                "id": uid,
                "index": unit_index,
                "from_line": start,
                "to_line": end - 1,
                "preview": cue_text(chunk[0]) if chunk else "",
                "line_indexes": list(range(start, end)),
                "skills": skills,
            }
        )
    word_total = len(words)
    sent_total = len(sentences)
    unit_total = len(units)
    word_done = sum(1 for item in words if item["key"] in mastered_words)
    sent_done = sum(1 for item in sentences if item["key"] in mastered_sents)
    words_ok = (not word_total) or word_done >= word_total
    sents_ok = sent_total > 0 and sent_done >= sent_total
    cleared = bool(
        unit_total
        and words_ok
        and sents_ok
        and read_done >= unit_total
        and sing_done >= unit_total
    )
    return {
        "schema": CAMPAIGN_SCHEMA,
        "song_id": _norm(song.get("id") or timeline.get("song_id")),
        "title": _norm(song.get("title") or timeline.get("title")),
        "artist": _norm(song.get("artist") or timeline.get("artist")),
        "language": _norm(song.get("language") or timeline.get("language")),
        "lines": lines,
        "goal": {
            "words": {"done": word_done, "total": word_total},
            "sentences": {"done": sent_done, "total": sent_total},
            "read": {"done": read_done, "total": unit_total},
            "sing": {"done": sing_done, "total": unit_total},
            "cleared": cleared,
        },
        "mistakes": int(mistakes),
        "units": units,
        "skills": list(SKILLS),
        "pass_pct": PASS_PCT,
        "modes": ["quiz", "tap", "echo"],
    }


def _attach_line(item: dict[str, Any], line: dict[str, Any]) -> dict[str, Any]:
    item["line_index"] = line["index"]
    item["start_ms"] = line["start_ms"]
    item["end_ms"] = line["end_ms"]
    item["romaji"] = line.get("romaji") or ""
    item["translation"] = line.get("translation") or line.get("zh") or ""
    return item


def _knowledge(kind: str, key: str, text: str, zh: str = "") -> dict[str, str]:
    return {"kind": kind, "key": key, "text": text, "zh": zh}


def _mc(
    qid: str,
    kind: str,
    prompt: str,
    stem: str,
    choices: list[dict[str, Any]],
    knowledge: dict[str, str],
) -> dict[str, Any]:
    item = _question(qid, kind, prompt, stem, choices)
    item["knowledge"] = knowledge
    answer = next((choice for choice in choices if choice.get("ok")), None)
    item["answer_text"] = _norm(answer["text"] if answer else "")
    return item


def _word_script_variant(token: dict[str, Any], japanese: bool) -> tuple[str, str]:
    """Return (shown stem, expected choice) using persisted lyric metadata."""
    text = _norm(token.get("surface") or token.get("text"))
    if not japanese:
        return _norm(token.get("translation") or token.get("zh")) or text, text
    # `reading` is produced by the lyrics pipeline for kanji. Never convert it
    # here: script choice is part of the persisted lyric data and must stay
    # faithful to the song.
    reading = _norm(token.get("reading"))
    # For kanji, the persisted reading is the expected hiragana answer. For
    # kana words the persisted `text` already carries the canonical script;
    # never convert it or substitute a derived reading.
    return text, reading if _has_kanji(text) and reading else text


def _match_item(
    qid: str,
    prompt: str,
    pairs: list[dict[str, str]],
    knowledge: dict[str, str],
) -> dict[str, Any]:
    return {
        "id": qid,
        "kind": "match",
        "prompt": prompt,
        "stem": "",
        "pairs": [
            {
                "id": index,
                "left": pair["left"],
                "right": pair["right"],
                "key": pair.get("key") or pair["left"],
            }
            for index, pair in enumerate(pairs)
        ],
        "knowledge": knowledge,
        "answer_text": " / ".join(pair["right"] for pair in pairs),
    }


def _word_items(
    unit_id: str,
    lines: list[dict[str, Any]],
    cues: list[dict[str, Any]],
    pools: dict[str, list[str]],
    rng: Any,
    lang: str,
    language: str = "",
) -> list[dict[str, Any]]:
    """Build word-recognition drills without leaking the target word.

    Sentence dictation belongs to the separate ``listen`` skill.  Here the
    learner sees a gloss and picks the matching lyric token, so the prompt
    never contains the answer itself.
    """
    items: list[dict[str, Any]] = []
    words = knowledge_words(cues)
    japanese = language == "ja"
    token_rows = [
        token
        for cue in cues
        for token in (cue.get("tokens") or [])
        if isinstance(token, dict) and _norm(token.get("text"))
    ]
    variants = {
        _norm(token.get("text")): _word_script_variant(token, japanese)
        for token in token_rows
    }
    variant_pool = _unique(
        [variant[1] for variant in variants.values()]
        + ([] if japanese else list(pools.get("word_text") or []))
    )
    # `pools` is built from the whole song, so reverse questions still have
    # meaningful Chinese distractors when a unit contains only a few words.
    gloss_pool = _unique(pools.get("zh") or [word["zh"] for word in words if word.get("zh")])
    for offset, word in enumerate(words):
        stem, answer = variants.get(word["text"], (word["text"], word["text"]))
        has_script_pair = bool(
            japanese
            and word.get("zh")
        )
        meaning_to_kana = False
        if has_script_pair:
            # Alternate the direction deterministically per lesson: meaning →
            # kana and kana → meaning are both useful, and neither prompt
            # contains the answer.
            if rng.random() < 0.5:
                meaning_to_kana = True
                choice_answer = answer
                choice_pool = variant_pool
                question_stem = word["zh"]
            else:
                choice_answer = word["zh"]
                choice_pool = gloss_pool
                question_stem = answer
        else:
            choice_answer = answer
            choice_pool = variant_pool
            question_stem = stem
        # Do not offer the other script of the same token as a competing
        # answer; it is a useful distractor only for a different token.
        own_forms = {answer}
        item_pool = [value for value in choice_pool if value not in own_forms]
        fallback = ("あ", "カ", "ア") if meaning_to_kana else ("其他", "某物", "—")
        item = _mc(
            f"{unit_id}:word:{offset}",
            "word",
            "",
            question_stem,
            _choices(choice_answer, item_pool, rng, fallback=fallback),
            _knowledge("word", word["key"], word["text"], word["zh"]),
        )
        host = next(
            (
                line
                for line in lines
                if any(tok.get("text") == word["text"] for tok in line.get("words") or [])
            ),
            lines[0] if lines else None,
        )
        if host:
            _attach_line(item, host)
            # The full-line romaji would reveal the answer before the learner
            # chooses a script variant, so keep this drill visual.
            item["romaji"] = ""
        items.append(item)
    rng.shuffle(items)
    return items


def _sentence_items(
    unit_id: str,
    lines: list[dict[str, Any]],
    cues: list[dict[str, Any]],
    pools: dict[str, list[str]],
    rng: Any,
    lang: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    glossed = [line for line, cue in zip(lines, cues) if has_useful_zh(cue)]
    if len(glossed) >= 2:
        picked = glossed[:4]
        items.append(
            _match_item(
                f"{unit_id}:smatch:0",
                translate(lang, "api.learn_match"),
                [
                    {"left": line["text"], "right": line["zh"], "key": _norm(line["text"])}
                    for line in picked
                ],
                _knowledge("sentence", _norm(picked[0]["text"]), picked[0]["text"], picked[0]["zh"]),
            )
        )
    for offset, (line, cue) in enumerate(zip(lines, cues)):
        knowledge = _knowledge("sentence", _norm(line["text"]), line["text"], line["zh"])
        if has_useful_zh(cue):
            item = _mc(
                f"{unit_id}:meaning:{offset}",
                "meaning",
                translate(lang, "api.learn_meaning"),
                line["text"],
                _choices(line["zh"], pools["zh"], rng),
                knowledge,
            )
            items.append(_attach_line(item, line))
            reverse = _mc(
                f"{unit_id}:reverse:{offset}",
                "reverse",
                translate(lang, "api.learn_reverse"),
                line["zh"],
                _choices(line["text"], pools["text"], rng),
                knowledge,
            )
            items.append(_attach_line(reverse, line))
        else:
            item = _mc(
                f"{unit_id}:listen:{offset}",
                "listen",
                translate(lang, "api.learn_listen"),
                line["text"],
                _choices(line["text"], pools["text"], rng),
                knowledge,
            )
            items.append(_attach_line(item, line))
    # Keep at least one question for every sentence so sentence mastery is
    # reachable even when the optional matching/reverse variants push the
    # lesson over the nominal size.
    rng.shuffle(items)
    return items


def _listen_items(
    unit_id: str,
    lines: list[dict[str, Any]],
    cues: list[dict[str, Any]],
    pools: dict[str, list[str]],
    rng: Any,
    lang: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for offset, (line, cue) in enumerate(zip(lines, cues)):
        knowledge = _knowledge("sentence", _norm(line["text"]), line["text"], line["zh"])
        listen = _mc(
            f"{unit_id}:listen:{offset}",
            "listen",
            translate(lang, "api.learn_listen"),
            line["text"],
            _choices(line["text"], pools["text"], rng),
            knowledge,
        )
        items.append(_attach_line(listen, line))
        if has_useful_zh(cue):
            meaning = _mc(
                f"{unit_id}:lmeaning:{offset}",
                "listen",
                translate(lang, "api.learn_listen_meaning"),
                "",
                _choices(line["zh"], pools["zh"], rng),
                knowledge,
            )
            items.append(_attach_line(meaning, line))
    rng.shuffle(items)
    return items[:LESSON_SIZE]


def build_lesson(
    timeline: dict[str, Any],
    song: dict[str, Any] | None,
    unit_id: str,
    skill: str,
    lang: str = "zh",
) -> dict[str, Any]:
    song = song or {}
    cues = singable_cues(timeline, song)
    units = chunk_units(cues)
    try:
        unit_index = int(str(unit_id).lstrip("u") or "0")
    except ValueError:
        unit_index = -1
    if unit_index < 0 or unit_index >= len(units):
        return {}
    chunk = units[unit_index]
    start = sum(len(part) for part in units[:unit_index])
    lines = [line_record(cue, start + offset) for offset, cue in enumerate(chunk)]
    pools = _line_pools(cues)
    song_id = _norm(song.get("id") or timeline.get("song_id"))
    rng = _seeded_rng(CAMPAIGN_SCHEMA, song_id, unit_id, skill)
    skill = skill if skill in SKILLS else ""
    play_mode = _SKILL_PLAY.get(skill)
    items: list[dict[str, Any]] = []
    if skill == "word":
        language = _norm(song.get("language") or timeline.get("language"))
        items = _word_items(unit_id, lines, chunk, pools, rng, lang, language)
        if not items:
            items = _listen_items(unit_id, lines, chunk, pools, rng, lang)
    elif skill == "sentence":
        items = _sentence_items(unit_id, lines, chunk, pools, rng, lang)
        if not items:
            items = _listen_items(unit_id, lines, chunk, pools, rng, lang)
    elif skill == "listen":
        items = _listen_items(unit_id, lines, chunk, pools, rng, lang)
    items = [
        item
        for item in items
        if (item.get("kind") == "match" and len(item.get("pairs") or []) >= 2)
        or len(item.get("choices") or []) >= 2
    ]
    return {
        "schema": CAMPAIGN_SCHEMA,
        "song_id": song_id,
        "title": _norm(song.get("title") or timeline.get("title")),
        "unit_id": unit_id,
        "skill": skill,
        "play_mode": play_mode,
        "lines": lines,
        "items": items,
        "total": len(items) if items else len(lines),
        "pass_pct": PASS_PCT,
    }


def item_from_mistake(row: dict[str, Any]) -> dict[str, Any] | None:
    payload = row.get("item") if isinstance(row.get("item"), dict) else {}
    if not payload:
        raw = row.get("payload") or ""
        if isinstance(raw, str) and raw.startswith("{"):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
    if not payload:
        return None
    item = dict(payload)
    item.setdefault("id", f"review:{row.get('qkind')}:{row.get('item_key')}")
    item.setdefault("kind", row.get("qkind") or "word")
    item.setdefault("prompt", row.get("prompt") or "")
    item.setdefault("stem", row.get("stem") or "")
    item.setdefault("answer_text", row.get("answer_text") or "")
    item.setdefault(
        "knowledge",
        {
            "kind": "word" if item.get("kind") in {"word", "blank", "match"} else "sentence",
            "key": row.get("item_key") or "",
            "text": row.get("stem") or row.get("item_key") or "",
            "zh": row.get("answer_text") or "",
        },
    )
    return item


def build_review_lesson(
    timeline: dict[str, Any],
    song: dict[str, Any] | None,
    mistakes: list[dict[str, Any]],
    lang: str = "zh",
) -> dict[str, Any]:
    del lang
    song = song or {}
    cues = singable_cues(timeline, song)
    lines = [line_record(cue, index) for index, cue in enumerate(cues)]
    items: list[dict[str, Any]] = []
    for row in mistakes:
        item = item_from_mistake(row)
        if not item:
            continue
        items.append(item)
        if len(items) >= REVIEW_SIZE:
            break
    return {
        "schema": CAMPAIGN_SCHEMA,
        "song_id": _norm(song.get("id") or timeline.get("song_id")),
        "title": _norm(song.get("title") or timeline.get("title")),
        "unit_id": "review",
        "skill": "review",
        "play_mode": None,
        "lines": lines,
        "items": items,
        "total": len(items),
        "pass_pct": PASS_PCT,
        "review": True,
    }


def apply_lesson_result(
    owner: str,
    song_id: str,
    unit_id: str,
    skill: str,
    *,
    pct: int,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = int(pct) >= PASS_PCT
    progress = None
    if skill in SKILLS:
        progress = learn_store.upsert_progress(
            owner, song_id, unit_id, skill, pct=pct, passed=passed
        )
    open_before = len(learn_store.list_mistakes(owner, song_id, open_only=True))
    for raw in answers:
        ok = bool(raw.get("ok"))
        knowledge = raw.get("knowledge") if isinstance(raw.get("knowledge"), dict) else {}
        qkind = _norm(
            raw.get("qkind") or raw.get("item_kind") or knowledge.get("qkind") or ""
        )
        if qkind not in {"word", "meaning", "listen", "match", "blank", "reverse"}:
            maybe = _norm(raw.get("kind"))
            qkind = maybe if maybe in {"word", "meaning", "listen", "match", "blank", "reverse"} else "word"
        kind = _norm(knowledge.get("kind") or raw.get("know") or "")
        if kind not in {"word", "sentence"}:
            kind = "word" if qkind in {"word", "blank", "match"} else "sentence"
        key = _norm(raw.get("key") or knowledge.get("key"))
        text = _norm(raw.get("text") or knowledge.get("text") or key)
        zh = _norm(raw.get("zh") or knowledge.get("zh") or raw.get("answer_text"))
        if kind in {"word", "sentence"} and key:
            learn_store.apply_mastery(
                owner, song_id, kind, key, text=text, zh=zh, ok=ok
            )
        if not key:
            continue
        if ok:
            learn_store.note_correct(owner, song_id, qkind, key)
        else:
            payload = raw.get("payload")
            if not isinstance(payload, dict):
                payload = {
                    "id": raw.get("id"),
                    "kind": qkind,
                    "prompt": raw.get("prompt") or "",
                    "stem": raw.get("stem") or text,
                    "choices": raw.get("choices") or [],
                    "answer": raw.get("answer"),
                    "pairs": raw.get("pairs") or [],
                    "blank": raw.get("blank"),
                    "start_ms": raw.get("start_ms"),
                    "end_ms": raw.get("end_ms"),
                    "line_index": raw.get("line_index"),
                    "knowledge": {
                        "kind": kind or "word",
                        "key": key,
                        "text": text,
                        "zh": zh,
                    },
                    "answer_text": raw.get("answer_text") or zh,
                }
            learn_store.record_mistake(
                owner,
                song_id,
                qkind=qkind,
                item_key=key,
                prompt=_norm(raw.get("prompt")),
                stem=_norm(raw.get("stem") or text),
                answer_text=_norm(raw.get("answer_text") or zh),
                payload=payload,
            )
    return {
        "progress": progress,
        "passed": passed,
        "pct": int(pct),
        "mistakes": len(learn_store.list_mistakes(owner, song_id, open_only=True)),
        "mistakes_before": open_before,
    }
