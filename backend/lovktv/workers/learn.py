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
# Credits / metadata lines that leak in from LRC files ("词：周杰伦",
# "Guitar: ...").  They are not lyrics and must never become questions.
_CREDIT_LINE = re.compile(
    r"^(?:词|曲|作词|作曲|编曲|編曲|作詞|填词|填詞|监制|監製|制作|製作|出品|"
    r"合声|合聲|和声|和聲|吉他|贝斯|貝斯|鼓|键盘|鍵盤|弦乐|弦樂|混音|母带|母帶|"
    r"录音|錄音|演唱|歌手|原唱|翻唱|歌|唄|"
    r"lyrics?|lyricist|music|composer|composed|arranged?|arranger|arrangement|"
    r"producer|produced|vocals?|guitar|bass|drums|keyboards?|piano|strings|"
    r"mix(?:ed|ing)?|master(?:ed|ing)?|written|performed)"
    r"[^:：\s]{0,6}\s*(?:by)?\s*[:：]\s*\S",
    re.I,
)
_SOLFEGE = {"do", "re", "mi", "fa", "so", "sol", "la", "si", "ti"}
# Interjections and vocalisations ("语气词").  A line made only of these is
# not a real sentence, and a token in this set is never worth a word drill.
_FILLER = {
    # zh
    "啊", "阿", "哦", "噢", "喔", "呀", "呢", "吧", "嘛", "哟", "唷", "哈", "嗯",
    "呜", "嘿", "哎", "唉", "诶", "耶", "哇", "嗨", "啦", "咯", "喽", "呐", "呦",
    "哼", "唔", "嘞", "欸", "嗷", "咦", "哩", "呵", "嘻",
    # ja kana
    "あ", "あぁ", "ああ", "あー", "う", "うー", "うぅ", "お", "おお", "おー", "おう",
    "え", "えー", "ええ", "ん", "うん", "ね", "ねえ", "ねぇ", "ねー", "よ", "な",
    "なあ", "なぁ", "さ", "さあ", "さぁ", "わ", "ぞ", "ぜ", "へい", "ふう", "ふー",
    "ほう", "らら", "ら", "わあ", "わぁ",
    "ア", "アー", "アア", "アァ", "オ", "オオ", "オー", "オウ", "ウ", "ウー",
    "ウォウ", "ウォー", "ウォ", "エ", "エー", "ヘイ", "イェイ", "イェー", "イエー",
    "イエイ", "ラ", "ララ", "ワオ", "フー", "フウ", "ハ", "ハー", "ヤ", "ヤー", "オイ",
    # romaji / english
    "a", "aa", "ah", "aah", "ahh", "o", "oo", "oh", "ooh", "ou", "u", "uu", "uh",
    "e", "ee", "eh", "n", "un", "ne", "nee", "yo", "na", "naa", "sa", "saa",
    "wa", "zo", "ze", "hei", "hey", "wou", "wow", "woah", "whoa", "woo", "fuu",
    "fu", "la", "ra", "yeah", "yea", "yay", "ya", "hmm", "hm", "mm", "mmm",
    "um", "umm", "huh", "ha", "haha", "ho", "hoo", "ey", "ay", "yah", "ooo",
    "ohh", "ohhh", "da", "du", "dum", "doo", "tu", "ru", "turu", "lu", "pa",
    "sha", "shala", "dubi", "ba", "bam",
}
_FILLER_GLOSS = {
    "啊", "哦", "噢", "喔", "呀", "呢", "吧", "嘛", "哟", "哈", "嗯", "呜", "嘿",
    "哎", "唉", "耶", "哇", "嗨", "啦", "咯", "喽", "呐", "哼", "唔", "欸", "诶",
    "呦", "哩",
}
_ELONGATION = re.compile(
    r"[~～〜ーｰ\-_.!?！？、。,…'\"“”‘’()（）\[\]「」『』♪\sぁぃぅぇぉァィゥェォ]+"
)
_REPEAT = re.compile(r"(.{1,4}?)\1+")
_WRAP_PAREN = re.compile(r"^[（(\[「『【]+(.*?)[）)\]」』】]+$")
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
    "no",
    "ni",
    "wo",
    "ga",
    "wa",
    "to",
    "mo",
    "de",
    "te",
    "ka",
    "he",
    "ya",
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


def _collapse(text: str) -> str:
    """Lower-case, drop elongation/punctuation, fold repeats ("ahhh"→"ah")."""
    folded = _ELONGATION.sub("", _norm(text).lower())
    previous = None
    while folded != previous:
        previous = folded
        folded = _REPEAT.sub(r"\1", folded)
    return folded


def is_filler_word(text: Any, gloss: Any = "") -> bool:
    """True for interjections / vocalisations such as "ah~", "ね", "哦"."""
    raw = _norm(text)
    if not raw:
        return True
    if _PUNCT.match(raw):
        return True
    folded = _collapse(raw)
    if not folded or folded in _FILLER:
        return True
    if folded.isascii() and folded in _SOLFEGE:
        return True
    gloss_folded = _collapse(gloss)
    if gloss_folded and gloss_folded in _FILLER_GLOSS:
        return True
    return False


def _line_units(text: str) -> list[str]:
    """Split a line into the units a filler check should look at."""
    if _LATIN_SPLIT.search(text) or " " in text:
        return [part for part in re.split(r"[\s,、，]+", text) if part]
    return [ch for ch in text if ch.strip()]


def is_filler_line(cue: dict[str, Any]) -> bool:
    """True when a line carries no real sentence: only "ah ah", "la la la"…"""
    text = _norm(cue.get("text") or cue.get("source_text"))
    wrapped = _WRAP_PAREN.match(text)
    if wrapped:
        text = wrapped.group(1).strip()
    if not text:
        return True
    if _collapse(text) in _FILLER:
        return True
    tokens = [
        tok
        for tok in (cue.get("tokens") or [])
        if isinstance(tok, dict) and _norm(tok.get("surface") or tok.get("text"))
    ]
    if tokens:
        units = [
            (
                _norm(tok.get("surface") or tok.get("text")),
                _norm(tok.get("translation") or tok.get("zh")),
            )
            for tok in tokens
        ]
    else:
        units = [(unit, "") for unit in _line_units(text)]
    if all(is_filler_word(unit, gloss) for unit, gloss in units):
        return True
    folded = [_collapse(unit) for unit, _ in units]
    folded = [unit for unit in folded if unit]
    if len(folded) >= 3 and all(unit in _SOLFEGE for unit in folded):
        return True
    return False


def _credit_key(value: Any) -> str:
    return re.sub(r"[\s\-–—_·・:：|/()（）\[\]]+", "", _norm(value).lower())


_TITLE_DASH = re.compile(r"^(.{1,40}?)\s+[-–—]\s+(.{1,40})$")
_TRAILING_PAREN = re.compile(r"\s*[（(\[【][^）)\]】]*[）)\]】]\s*$")


def is_credit_line(
    cue: dict[str, Any],
    song: dict[str, Any] | None = None,
    position: int | None = None,
) -> bool:
    """True for LRC metadata: "词：…", "Guitar: …", or the "title - artist" line.

    ``position`` is the cue's index in the song; the loose "X - Y" title
    heuristic only applies to the first few lines where such headers live.
    """
    text = _norm(cue.get("text") or cue.get("source_text"))
    if len(text) <= 40 and _CREDIT_LINE.match(text):
        return True
    song = song or {}
    title = _credit_key(song.get("title"))
    artist = _credit_key(song.get("artist"))
    key = _credit_key(text)
    if not key:
        return False
    if title and len(title) >= 2 and artist and len(artist) >= 2:
        if title in key and artist in key:
            return True
    for name in (title, artist):
        if name and len(name) >= 2 and key == name:
            return True
    if position is not None and position < 3:
        dash = _TITLE_DASH.match(_TRAILING_PAREN.sub("", text))
        if dash:
            halves = [_credit_key(part) for part in dash.groups()]
            for half in halves:
                if len(half) < 2:
                    continue
                for name in (title, artist):
                    if name and (half in name or name in half):
                        return True
    return False


def is_singable_cue(
    cue: dict[str, Any],
    song: dict[str, Any] | None = None,
    position: int | None = None,
) -> bool:
    text = _norm(cue.get("text") or cue.get("source_text"))
    if len(text) < 2:
        return False
    if _SKIP_LINE.match(text) is not None:
        return False
    if is_credit_line(cue, song, position):
        return False
    return not is_filler_line(cue)


def cue_text(cue: dict[str, Any]) -> str:
    return _norm(cue.get("text") or cue.get("source_text"))


def cue_zh(cue: dict[str, Any]) -> str:
    return _norm(cue.get("translation") or cue.get("zh"))


def cue_romaji(cue: dict[str, Any]) -> str:
    bits = [
        _norm(
            tok.get("romaji")
            or ((tok.get("pronunciation") or {}).get("value") if isinstance(tok.get("pronunciation"), dict) else "")
        )
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
        text = _norm(token.get("surface") or token.get("text"))
        if not text or _PUNCT.match(text):
            continue
        translation = _norm(token.get("translation") or token.get("zh"))
        romaji = _norm(
            token.get("romaji")
            or (
                (token.get("pronunciation") or {}).get("value")
                if isinstance(token.get("pronunciation"), dict)
                else ""
            )
        )
        words.append(
            {
                "text": text,
                "romaji": romaji,
                "translation": translation,
                "zh": translation,
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
        text = _norm(token.get("surface") or token.get("text"))
        zh = _norm(token.get("translation") or token.get("zh"))
        if not text or not zh or zh == text:
            continue
        if is_filler_word(text, zh):
            continue
        if not include_function and text.lower() in _FUNCTION:
            continue
        key = (text, zh)
        if key in seen:
            continue
        seen.add(key)
        found.append({"text": text, "zh": zh})
    return found


def quiz_words(cue: dict[str, Any]) -> list[dict[str, str]]:
    """Words worth drilling on a line: content words first, particles only
    when the line has nothing else."""
    words = content_tokens(cue, include_function=False)
    return words or content_tokens(cue, include_function=True)


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
    words = [token for cue in cues for token in content_tokens(cue, include_function=False)]
    if len(_unique([token["zh"] for token in words])) < 4:
        words = [token for cue in cues for token in content_tokens(cue, include_function=True)]
    return {
        "zh": _unique([cue_zh(cue) for cue in cues if has_useful_zh(cue)]),
        "text": _unique([cue_text(cue) for cue in cues]),
        "word": _unique([token["zh"] for token in words]),
        "word_text": _unique([token["text"] for token in words]),
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
    for offset, word in enumerate(quiz_words(cue)):
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


def _song_meta(timeline: dict[str, Any], song: dict[str, Any] | None) -> dict[str, Any]:
    song = song or {}
    return {
        "title": song.get("title") or timeline.get("title") or "",
        "artist": song.get("artist") or timeline.get("artist") or "",
    }


def build_learn_quiz(
    timeline: dict[str, Any], song: dict[str, Any] | None = None, lang: str = "zh"
) -> dict[str, Any]:
    song = song or {}
    meta = _song_meta(timeline, song)
    cues = [
        cue
        for position, cue in enumerate(timeline.get("cues") or [])
        if isinstance(cue, dict) and is_singable_cue(cue, meta, position)
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
