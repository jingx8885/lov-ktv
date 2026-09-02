"""Build mixed lyric-meaning + word-gloss quizzes from a song timeline."""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from typing import Any

QUESTIONS_PER_LINE = 1
LEARN_SCHEMA = "lovktv-learn-v1"

_SKIP_LINE = re.compile(
    r"^(instrumental|inst\.?|間奏|间奏|前奏|间奏中|outro|intro|bridge|♪+|…+|\.+)$",
    re.I,
)
_FUNCTION = {
    "の",
    "に",
    "を",
    "は",
    "が",
    "と",
    "も",
    "で",
    "て",
    "た",
    "だ",
    "よ",
    "ね",
    "な",
    "ん",
    "か",
    "へ",
    "や",
    "ば",
    "ず",
    "ぬ",
    "a",
    "an",
    "the",
    "to",
    "of",
    "in",
    "on",
    "at",
    "is",
    "are",
    "was",
    "and",
    "or",
    "i",
    "you",
    "we",
    "my",
    "me",
    "it",
    "的",
    "了",
    "着",
    "在",
    "是",
    "和",
    "吗",
    "呢",
    "吧",
    "啊",
}
_FALLBACK_ZH = (
    "昨天",
    "明天",
    "一个人",
    "回家",
    "下雨",
    "微笑",
    "夜晚",
    "记忆",
    "旅程",
    "心跳",
    "远方",
    "春天",
    "秘密",
    "眼泪",
    "阳光",
    "风",
)
_PUNCT = re.compile(r"^[\s.,!?;:…。、！？・～~'\"“”‘’（）()「」『』【】\[\]/\\-]+$")
_LATIN_SPLIT = re.compile(r"[A-Za-z]")


def _norm(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _seeded_rng(*parts: Any) -> random.Random:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def is_singable_cue(cue: dict[str, Any]) -> bool:
    text = _norm(cue.get("text") or cue.get("source_text"))
    if len(text) < 2:
        return False
    return _SKIP_LINE.match(text) is None


def cue_text(cue: dict[str, Any]) -> str:
    return _norm(cue.get("text") or cue.get("source_text"))


def cue_zh(cue: dict[str, Any]) -> str:
    return _norm(cue.get("zh"))


def cue_romaji(cue: dict[str, Any]) -> str:
    bits = [
        _norm(tok.get("romaji"))
        for tok in cue.get("tokens") or []
        if isinstance(tok, dict)
    ]
    joined = " ".join(bit for bit in bits if bit)
    return joined or _norm(cue.get("romaji"))


def has_useful_zh(cue: dict[str, Any]) -> bool:
    zh = cue_zh(cue)
    return bool(zh) and zh != cue_text(cue)


def tap_words(cue: dict[str, Any]) -> list[dict[str, str]]:
    """Surface tokens in sung order. Punctuation is dropped; function words stay."""
    words: list[dict[str, str]] = []
    for token in cue.get("tokens") or []:
        if not isinstance(token, dict):
            continue
        text = _norm(token.get("text"))
        if not text or _PUNCT.match(text):
            continue
        words.append(
            {
                "text": text,
                "romaji": _norm(token.get("romaji")),
                "zh": _norm(token.get("zh")),
            }
        )
    if words:
        return words
    text = cue_text(cue)
    if _LATIN_SPLIT.search(text):
        return [
            {"text": part, "romaji": "", "zh": ""}
            for part in text.split()
            if part and not _PUNCT.match(part)
        ]
    chars = [ch for ch in text if ch.strip() and not _PUNCT.match(ch)]
    if len(chars) >= 2:
        return [{"text": ch, "romaji": "", "zh": ""} for ch in chars]
    if text:
        return [{"text": text, "romaji": cue_romaji(cue), "zh": cue_zh(cue)}]
    return []


def content_tokens(
    cue: dict[str, Any], *, include_function: bool = False
) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for token in cue.get("tokens") or []:
        if not isinstance(token, dict):
            continue
        text = _norm(token.get("text"))
        zh = _norm(token.get("zh"))
        if not text or not zh or zh == text:
            continue
        if not include_function and text.lower() in _FUNCTION:
            continue
        key = (text, zh)
        if key in seen:
            continue
        seen.add(key)
        found.append({"text": text, "zh": zh})
    return found


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        text = _norm(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _choices(
    correct: str,
    pool: list[str],
    rng: random.Random,
    extra: tuple[str, ...] = (),
    fallback: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    answer = _norm(correct)
    distractors: list[str] = []
    seen = {answer}
    fallback_pool = list(_FALLBACK_ZH if fallback is None else fallback)
    # Prefer real distractors from the same semantic pool.  Fallback labels
    # should only fill a genuinely tiny pool; mixing "—/…" into a normal word
    # question makes the exercise look like a broken multiple-choice item.
    for item in pool + list(extra):
        text = _norm(item)
        if not text or text in seen:
            continue
        seen.add(text)
        distractors.append(text)
        if len(distractors) >= 8:
            break
    if len(distractors) < 3:
        for item in fallback_pool:
            text = _norm(item)
            if not text or text in seen:
                continue
            seen.add(text)
            distractors.append(text)
            if len(distractors) >= 3:
                break
    rng.shuffle(distractors)
    picked = distractors[:3]
    while len(picked) < 3:
        filler = fallback_pool[len(picked) % len(fallback_pool)] if fallback_pool else "…"
        if filler != answer and filler not in picked:
            picked.append(filler)
        else:
            from lovktv.locale.i18n import translate

            picked.append(translate("zh", "api.learn_option", n=len(picked) + 1))
    options = [answer, *picked]
    rng.shuffle(options)
    return [
        {"id": index, "text": text, "ok": text == answer}
        for index, text in enumerate(options)
    ]


def _question(
    qid: str,
    kind: str,
    prompt: str,
    stem: str,
    choices: list[dict[str, Any]],
) -> dict[str, Any]:
    answer = next((item["id"] for item in choices if item.get("ok")), 0)
    return {
        "id": qid,
        "kind": kind,
        "prompt": prompt,
        "stem": stem,
        "choices": [{"id": item["id"], "text": item["text"]} for item in choices],
        "answer": answer,
    }


def _line_pools(cues: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "zh": _unique([cue_zh(cue) for cue in cues if has_useful_zh(cue)]),
        "text": _unique([cue_text(cue) for cue in cues]),
        "word": _unique(
            [
                token["zh"]
                for cue in cues
                for token in content_tokens(cue, include_function=True)
            ]
        ),
        "word_text": _unique(
            [
                token["text"]
                for cue in cues
                for token in content_tokens(cue, include_function=True)
            ]
        ),
    }


def build_line_questions(
    cue: dict[str, Any],
    index: int,
    pools: dict[str, list[str]],
    rng: random.Random,
    lang: str = "zh",
) -> list[dict[str, Any]]:
    """One live question per sung line, drawn from that line's bank."""
    from lovktv.locale.i18n import translate

    bank: list[dict[str, Any]] = []
    text = cue_text(cue)
    if has_useful_zh(cue):
        bank.append(
            _question(
                f"{index}:meaning:0",
                "meaning",
                translate(lang, "api.learn_meaning"),
                text,
                _choices(cue_zh(cue), pools["zh"], rng),
            )
        )
    for offset, word in enumerate(content_tokens(cue, include_function=True)):
        bank.append(
            _question(
                f"{index}:word:{offset}",
                "word",
                translate(lang, "api.learn_word", word=word["text"]),
                word["text"],
                _choices(word["zh"], pools["word"], rng),
            )
        )
    if not bank and text:
        bank.append(
            _question(
                f"{index}:listen:0",
                "listen",
                translate(lang, "api.learn_listen"),
                text,
                _choices(text, pools["text"], rng),
            )
        )
    if not bank:
        return []
    return [rng.choice(bank)]


def build_learn_quiz(
    timeline: dict[str, Any], song: dict[str, Any] | None = None, lang: str = "zh"
) -> dict[str, Any]:
    song = song or {}
    cues = [
        cue
        for cue in (timeline.get("cues") or [])
        if isinstance(cue, dict) and is_singable_cue(cue)
    ]
    pools = _line_pools(cues)
    song_id = _norm(song.get("id") or timeline.get("song_id"))
    lines: list[dict[str, Any]] = []
    for index, cue in enumerate(cues):
        rng = _seeded_rng(LEARN_SCHEMA, song_id, index, cue_text(cue))
        questions = build_line_questions(cue, index, pools, rng, lang=lang)
        if not questions:
            continue
        lines.append(
            {
                "index": index,
                "start_ms": int(cue.get("start_ms") or 0),
                "end_ms": int(cue.get("end_ms") or 0),
                "text": cue_text(cue),
                "zh": cue_zh(cue),
                "romaji": cue_romaji(cue),
                "words": tap_words(cue),
                "questions": questions,
            }
        )
    return {
        "schema": LEARN_SCHEMA,
        "song_id": song_id,
        "title": _norm(song.get("title") or timeline.get("title")),
        "artist": _norm(song.get("artist") or timeline.get("artist")),
        "language": _norm(song.get("language") or timeline.get("language")),
        "modes": ["quiz", "tap", "echo"],
        "questions_per_line": QUESTIONS_PER_LINE,
        "lines": lines,
        "total_questions": sum(len(line["questions"]) for line in lines),
    }
