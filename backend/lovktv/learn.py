"""Build mixed lyric-meaning + word-gloss quizzes from a song timeline."""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from typing import Any

QUESTIONS_PER_LINE = 4
LEARN_SCHEMA = "lovktv-learn-v1"

_SKIP_LINE = re.compile(
    r"^(instrumental|inst\.?|間奏|间奏|前奏|间奏中|outro|intro|bridge|♪+|…+|\.+)$",
    re.I,
)
_FUNCTION = {
    "の", "に", "を", "は", "が", "と", "も", "で", "て", "た", "だ", "よ", "ね", "な", "ん", "か",
    "へ", "や", "ば", "ず", "ぬ",
    "a", "an", "the", "to", "of", "in", "on", "at", "is", "are", "was", "and", "or",
    "i", "you", "we", "my", "me", "it",
    "的", "了", "着", "在", "是", "和", "吗", "呢", "吧", "啊",
}
_FALLBACK_ZH = (
    "昨天", "明天", "一个人", "回家", "下雨", "微笑", "夜晚", "记忆", "旅程",
    "心跳", "远方", "春天", "秘密", "眼泪", "阳光", "风",
)


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
    bits = [_norm(tok.get("romaji")) for tok in cue.get("tokens") or [] if isinstance(tok, dict)]
    joined = " ".join(bit for bit in bits if bit)
    return joined or _norm(cue.get("romaji"))


def has_useful_zh(cue: dict[str, Any]) -> bool:
    zh = cue_zh(cue)
    return bool(zh) and zh != cue_text(cue)


def content_tokens(cue: dict[str, Any], *, include_function: bool = False) -> list[dict[str, str]]:
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


def _choices(correct: str, pool: list[str], rng: random.Random, extra: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    answer = _norm(correct)
    distractors: list[str] = []
    seen = {answer}
    for item in pool + list(extra) + list(_FALLBACK_ZH):
        text = _norm(item)
        if not text or text in seen:
            continue
        seen.add(text)
        distractors.append(text)
        if len(distractors) >= 8:
            break
    rng.shuffle(distractors)
    picked = distractors[:3]
    while len(picked) < 3:
        filler = _FALLBACK_ZH[len(picked) % len(_FALLBACK_ZH)]
        if filler != answer and filler not in picked:
            picked.append(filler)
        else:
            picked.append(f"选项{len(picked) + 1}")
    options = [answer, *picked]
    rng.shuffle(options)
    return [{"id": index, "text": text, "ok": text == answer} for index, text in enumerate(options)]


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
    }


def build_line_questions(
    cue: dict[str, Any],
    index: int,
    pools: dict[str, list[str]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    text = cue_text(cue)
    if has_useful_zh(cue):
        questions.append(
            _question(
                f"{index}:meaning:0",
                "meaning",
                "这句是什么意思？",
                text,
                _choices(cue_zh(cue), pools["zh"], rng),
            )
        )
    words = content_tokens(cue)
    if len(words) < QUESTIONS_PER_LINE - len(questions):
        extra = [item for item in content_tokens(cue, include_function=True) if item not in words]
        words = words + extra
    rng.shuffle(words)
    for offset, word in enumerate(words):
        if len(questions) >= QUESTIONS_PER_LINE:
            break
        questions.append(
            _question(
                f"{index}:word:{offset}",
                "word",
                f"「{word['text']}」是什么意思？",
                word["text"],
                _choices(word["zh"], pools["word"], rng),
            )
        )
    if len(questions) < QUESTIONS_PER_LINE and text:
        questions.append(
            _question(
                f"{index}:listen:0",
                "listen",
                "刚才唱的是哪一句？",
                text,
                _choices(text, pools["text"], rng),
            )
        )
    more_words = content_tokens(cue, include_function=True)
    for offset, word in enumerate(more_words, start=len(words)):
        if len(questions) >= QUESTIONS_PER_LINE:
            break
        if any(item.get("stem") == word["text"] for item in questions):
            continue
        questions.append(
            _question(
                f"{index}:word:{offset}",
                "word",
                f"「{word['text']}」是什么意思？",
                word["text"],
                _choices(word["zh"], pools["word"], rng),
            )
        )
    return questions[:QUESTIONS_PER_LINE]


def build_learn_quiz(timeline: dict[str, Any], song: dict[str, Any] | None = None) -> dict[str, Any]:
    song = song or {}
    cues = [cue for cue in (timeline.get("cues") or []) if isinstance(cue, dict) and is_singable_cue(cue)]
    pools = _line_pools(cues)
    song_id = _norm(song.get("id") or timeline.get("song_id"))
    lines: list[dict[str, Any]] = []
    for index, cue in enumerate(cues):
        rng = _seeded_rng(LEARN_SCHEMA, song_id, index, cue_text(cue))
        questions = build_line_questions(cue, index, pools, rng)
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
                "questions": questions,
            }
        )
    return {
        "schema": LEARN_SCHEMA,
        "song_id": song_id,
        "title": _norm(song.get("title") or timeline.get("title")),
        "artist": _norm(song.get("artist") or timeline.get("artist")),
        "language": _norm(song.get("language") or timeline.get("language")),
        "modes": ["quiz", "echo"],
        "questions_per_line": QUESTIONS_PER_LINE,
        "lines": lines,
        "total_questions": sum(len(line["questions"]) for line in lines),
    }
