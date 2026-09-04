"""Japanese lyric annotation agent: display kanji + hiragana above, katakana + English above.

This is not a word list. An LLM reads the whole lyric and returns units.
Results are cached per song so import/realign can reuse them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import httpx

from lovktv.domain.timeline import LyricToken

_KATAKANA = re.compile(r"[\u30a0-\u30ff]")
_KANJI = re.compile(r"[\u3400-\u9fff\uf900-\ufaff々]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_KATA_MARK = set("ー・ヽヾ")
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)
_LINE_NO = re.compile(r"^\d+\.\s*")
_INDEX_UNIT = re.compile(r"^\d+\.$")
_LATIN_PART = re.compile(r"[A-Za-z0-9']+(?:[!?.,…]+)?|[^\sA-Za-z0-9']+")
_LATIN_WORD = re.compile(r"[A-Za-z]+")
_HIRA = re.compile(r"[\u3040-\u309f]")
_KANJI_RUN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff々]+")
_HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_JA_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_LATIN_LETTER = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
# The agent also supplies Chinese line/unit meanings. Bump the cache schema so
# old literal glosses are regenerated after semantic-translation prompt changes.
ANNOTATION_SCHEMA = "restore-ja-v4"

SYSTEM = """You restore Japanese karaoke lyrics and annotate them.
Return JSON only:
{"lines":[{"source":"<exact original line>","translation":"...","units":[{"surface":"...","reading":"...","pronunciation":{"system":"romaji","value":"..."},"translation":"..."}]}]}

Rules:
Field names: `surface` (also called `sing`) is the Japanese text that is sung
and displayed; `reading` (also called `label`) is the hiragana reading or the
loanword's original English; `pronunciation.value` (also called `romaji`) is
Hepburn romaji; `translation` (also called `zh`) is Simplified Chinese.

1. `source` must equal the input line exactly, even when the input is romaji.
2. If the line is Hepburn romaji, restore Japanese in `surface` (kanji /
   ひらがな / カタカナ as the lyric is normally written). Example:
   "itsumo no you ni" → いつもの / ように; "tomatta hari" → 止まった / 針.
   NEVER put romaji in `surface` and never put the Japanese only in
   `reading`: `surface` must be Japanese, and the romaji goes in
   `pronunciation.value`.
3. Units cover the WHOLE sung line in order. Do not drop or invent words. If the source is romaji, every source word must become a unit (me magurushii jikan no mure ga → めまぐるしい / じかん / の / むれ / が).
4. Kanji / kanji+okurigana: `surface` is the original writing as in the lyric (止まった, 君, 溢れる); `reading` is the hiragana reading in THIS song (とまった, きみ, あふれる); `pronunciation.value` is Hepburn (tomatta, kimi). Split at word boundaries: 走り続ける → 走り / 続ける. Context: 君 as you → きみ, not くん.
5. Katakana loanwords (メモリー, コーヒー, ダンサー): `surface` is katakana; `reading` is the original English/French word (memory, coffee, dancer); `pronunciation.value` is empty. Never write memorii or koohii.
6. Native katakana (ズレ, フリ, ダメ): `surface` katakana; `reading` empty; `pronunciation.value` Hepburn (zure, furi).
7. Hiragana particles / leftover kana: `surface` as kana; `reading` empty; `pronunciation.value` Hepburn (no, ni, you).
8. Already-English words in the lyric (Give a reason, Here we go): keep them in
   `surface`, one English word per unit (never ``Give a reason`` as one unit);
   `reading` and `pronunciation.value` are empty. Every unit's romaji, when
   present, belongs to that unit only.
9. Every line MUST include `translation`: a faithful, clear Simplified Chinese translation of the whole sung line, written in Chinese characters. Never answer in English, romaji, or by copying the Japanese line. Keep close to the source wording and structure; use the complete line, surrounding input lines, song title, and artist to resolve meaning. Make only the smallest adjustment needed for understandable Chinese—do not freely paraphrase or add poetic information. Preserve agency, negation, tense/aspect, modality, and emotional tone. No notes, no brackets.
10. Every unit MUST include the `translation` key. Its value is a short *contextual contribution* in Chinese characters (usually 1–6 Chinese characters), not a dictionary definition and never an English word. If a Japanese word/compound is written in Hanzi that modern Chinese can directly understand, prefer copying that same Hanzi into `zh`, converting Japanese/traditional forms to Simplified Chinese as needed (for example, 電光石火 → 电光石火, not “转瞬即逝”). Only change it when it is a Japanese false friend or would mislead in this line.
11. Resolve remaining ambiguity from grammar and lyric context (for example, 君 can be “你” or “君”; miss can be “想念” or “错过”). Keep the closest understandable meaning, without freer poetic paraphrase.
12. Particles and function words are grammatical. Their `zh` may be empty (`""`) when Chinese word order or the whole-line translation already expresses them. If they add meaning, use the contextual relation; never use fixed mappings such as の→的, に→在, を→把, は→是. Do not force a Chinese word for every token.
13. Several source units may share one Chinese phrase, and a unit gloss may be empty when its meaning is absorbed by the phrase. Keep source coverage/order and let the faithful, clear line translation take priority over literal gloss alignment.
14. Before returning, compare every unit gloss with the completed `zh` line. Remove or revise any gloss that is a literal dictionary substitute but does not express that unit's role in this line.
"""


def agent_base_url() -> str:
    from lovktv.storage import settings

    raw = (
        settings.get("agent_url") or os.environ.get("OPENAI_BASE_URL") or ""
    ).rstrip("/")
    if not raw:
        return ""
    return raw if raw.endswith("/v1") else raw + "/v1"


def agent_api_key() -> str:
    from lovktv.storage import settings

    return settings.get("agent_key") or os.environ.get("OPENAI_API_KEY") or ""


def agent_model() -> str:
    from lovktv.storage import settings

    configured = settings.get("agent_model")
    if configured:
        return configured
    return (
        os.environ.get("LOVKTV_AGENT_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-5.4-mini"
    )


def agent_enabled() -> bool:
    from lovktv.storage import settings

    if not settings.get("ja_agent_enabled"):
        return False
    return bool(agent_base_url() and agent_api_key())


def agent_status() -> dict[str, Any]:
    return {
        "enabled": agent_enabled(),
        "model": agent_model() if agent_enabled() else "",
    }


def line_is_romaji(text: str) -> bool:
    source = lyric_source_key(text)
    if _KANA.search(source) or _KANJI.search(source):
        return False
    letters = [char for char in source if char.isalpha()]
    return bool(letters) and all(char.isascii() for char in letters)


def has_han(text: str) -> bool:
    """True when the text contains at least one Chinese character."""
    return bool(_HAN.search(unicodedata.normalize("NFKC", str(text or ""))))


def valid_zh(text: str) -> str:
    """Return a usable Chinese gloss/translation, or "" when the agent answered
    in English, romaji, punctuation, or copied a non-Chinese source."""
    body = str(text or "").strip()
    return body if has_han(body) else ""


def _unit_surface_text(unit: dict[str, Any]) -> str:
    return lyric_source_key(unit.get("surface") or unit.get("sing") or "")


def _unit_reading_text(unit: dict[str, Any]) -> str:
    return unicodedata.normalize(
        "NFKC", str(unit.get("reading") or unit.get("label") or "")
    ).strip()


def _unit_romaji_text(unit: dict[str, Any]) -> str:
    pronunciation = unit.get("pronunciation")
    pron_value = (
        str(pronunciation.get("value") or "").strip()
        if isinstance(pronunciation, dict)
        else ""
    )
    return str(unit.get("romaji") or pron_value).strip()


def unit_is_unrestored_romaji(unit: dict[str, Any]) -> bool:
    """The agent echoed romaji in ``surface`` and put the Japanese in ``reading``."""
    sing = _unit_surface_text(unit)
    if not sing or _KANA.search(sing) or _KANJI.search(sing):
        return False
    if not _LATIN_WORD.search(sing):
        return False
    reading = _unit_reading_text(unit)
    return bool(_KANA.search(reading) or _KANJI.search(reading))


_ROMAJI_MACRONS = str.maketrans({"ā": "aa", "ī": "ii", "ū": "uu", "ē": "ee", "ō": "ou"})
_ROMAJI_TABLE: dict[str, str] = {
    "kya": "きゃ", "kyu": "きゅ", "kyo": "きょ", "sha": "しゃ", "shu": "しゅ",
    "sho": "しょ", "sya": "しゃ", "syu": "しゅ", "syo": "しょ", "cha": "ちゃ",
    "chu": "ちゅ", "cho": "ちょ", "tya": "ちゃ", "tyu": "ちゅ", "tyo": "ちょ",
    "nya": "にゃ", "nyu": "にゅ", "nyo": "にょ", "hya": "ひゃ", "hyu": "ひゅ",
    "hyo": "ひょ", "mya": "みゃ", "myu": "みゅ", "myo": "みょ", "rya": "りゃ",
    "ryu": "りゅ", "ryo": "りょ", "gya": "ぎゃ", "gyu": "ぎゅ", "gyo": "ぎょ",
    "zya": "じゃ", "zyu": "じゅ", "zyo": "じょ", "jya": "じゃ", "jyu": "じゅ",
    "jyo": "じょ", "bya": "びゃ", "byu": "びゅ", "byo": "びょ", "pya": "ぴゃ",
    "pyu": "ぴゅ", "pyo": "ぴょ", "shi": "し", "chi": "ち", "tsu": "つ",
    "dzu": "づ", "she": "しぇ", "che": "ちぇ",
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ", "sa": "さ",
    "si": "し", "su": "す", "se": "せ", "so": "そ", "ta": "た", "ti": "ち",
    "tu": "つ", "te": "て", "to": "と", "na": "な", "ni": "に", "nu": "ぬ",
    "ne": "ね", "no": "の", "ha": "は", "hi": "ひ", "hu": "ふ", "fu": "ふ",
    "he": "へ", "ho": "ほ", "ma": "ま", "mi": "み", "mu": "む", "me": "め",
    "mo": "も", "ya": "や", "yu": "ゆ", "yo": "よ", "ra": "ら", "ri": "り",
    "ru": "る", "re": "れ", "ro": "ろ", "wa": "わ", "wi": "うぃ", "we": "うぇ",
    "wo": "を", "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "za": "ざ", "zi": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ", "ja": "じゃ",
    "ji": "じ", "ju": "じゅ", "je": "じぇ", "jo": "じょ", "da": "だ", "di": "ぢ",
    "du": "づ", "de": "で", "do": "ど", "ba": "ば", "bi": "び", "bu": "ぶ",
    "be": "べ", "bo": "ぼ", "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ",
    "po": "ぽ", "fa": "ふぁ", "fi": "ふぃ", "fe": "ふぇ", "fo": "ふぉ",
    "va": "ゔぁ", "vi": "ゔぃ", "vu": "ゔ", "ve": "ゔぇ", "vo": "ゔぉ",
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
}
_VOWELS = set("aiueo")
_ROMAJI_PARTICLES = {"wa": "は", "e": "へ", "wo": "を", "o": "お"}


def romaji_to_hiragana(text: str) -> str:
    """Convert one Hepburn / Kunrei romaji word to hiragana.

    Returns "" unless the whole word converts, so English words such as
    ``love`` or ``only`` are left alone.  Used for particles and short words
    the annotation agent echoed as romaji without any Japanese.
    """
    raw = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    raw = raw.translate(_ROMAJI_MACRONS).replace("’", "'")
    if not raw or not re.fullmatch(r"[a-z'\-~]+", raw):
        return ""
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char in "'~":
            index += 1
            continue
        if char == "-":
            out.append("ー")
            index += 1
            continue
        rest = raw[index:]
        nxt = raw[index + 1] if index + 1 < len(raw) else ""
        # syllabic ん: n before a consonant / apostrophe / end, m before b/p/m
        if char == "n" and (not nxt or (nxt not in _VOWELS and nxt != "y")):
            out.append("ん")
            index += 1
            continue
        if char == "m" and nxt in ("b", "p", "m") and nxt:
            out.append("ん")
            index += 1
            continue
        # sokuon: doubled consonant or t before ch
        if (
            char not in _VOWELS
            and char != "n"
            and nxt
            and (nxt == char or (char == "t" and rest.startswith("tch")))
        ):
            out.append("っ")
            index += 1
            continue
        for size in (3, 2, 1):
            kana = _ROMAJI_TABLE.get(rest[:size])
            if kana:
                out.append(kana)
                index += size
                break
        else:
            return ""
    return "".join(out)


def _romaji_matches(romaji: str, sing: str) -> bool:
    strip = lambda value: re.sub(r"[^a-z]", "", value.lower())  # noqa: E731
    return bool(strip(romaji)) and strip(romaji) == strip(sing)


def restore_romaji_unit(unit: dict[str, Any], source: str = "") -> dict[str, Any]:
    """Return a unit whose ``surface`` is Japanese, not romaji.

    Two agent mistakes are repaired:
    - ``surface=romaji / reading=Japanese``: the Japanese moves into
      ``surface``/``sing`` and the romaji is kept as the pronunciation.  A
      kanji reading is resolved later by ``expand_units`` (pykakasi).
    - a romaji-only line where a particle/word was echoed as romaji with no
      Japanese at all (``wa``, ``no``, ``dakedo``): converted to hiragana
      deterministically, but only when the romaji is the word itself so
      English lyrics are never touched.
    """
    sing = _unit_surface_text(unit)
    if unit_is_unrestored_romaji(unit):
        japanese = _unit_reading_text(unit)
        romaji = _unit_romaji_text(unit) or sing
        fixed = dict(unit)
        fixed["sing"] = japanese
        fixed["surface"] = japanese
        fixed["label"] = ""
        fixed["reading"] = ""
        fixed["romaji"] = romaji
        fixed["pronunciation"] = {"system": "romaji", "value": romaji}
        return fixed
    if not sing or _KANA.search(sing) or _KANJI.search(sing):
        return unit
    if source and not line_is_romaji(source):
        return unit
    reading = _unit_reading_text(unit)
    if reading and not _romaji_matches(reading, sing):
        return unit
    romaji = _unit_romaji_text(unit)
    if not romaji or not _romaji_matches(romaji, sing):
        return unit
    # A standalone ``wa`` / ``e`` unit is the topic / direction particle.
    kana = _ROMAJI_PARTICLES.get(sing.lower()) or romaji_to_hiragana(sing)
    if not kana:
        return unit
    fixed = dict(unit)
    fixed["sing"] = kana
    fixed["surface"] = kana
    fixed["label"] = ""
    fixed["reading"] = ""
    fixed["romaji"] = romaji
    fixed["pronunciation"] = {"system": "romaji", "value": romaji}
    return fixed


def japanese_from_units(units: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for unit in units:
        sing = lyric_source_key(unit.get("sing") or "")
        if not sing:
            continue
        if (
            parts
            and re.match(r"[A-Za-z0-9']", sing)
            and re.search(r"[A-Za-z0-9']$", parts[-1] or "")
        ):
            parts.append(" ")
        parts.append(sing)
    return "".join(parts)


def _is_katakana(text: str) -> bool:
    body = [char for char in text if not char.isspace()]
    return bool(body) and all(
        _KATAKANA.match(char) or char in _KATA_MARK for char in body
    )


def _source_hash(lines: list[str], title: str, artist: str) -> str:
    payload = json.dumps(
        {"schema": ANNOTATION_SCHEMA, "title": title, "artist": artist, "lines": lines},
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        data = json.loads(match.group(0)) if match else {}
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list):
        raise ValueError("agent 返回的不是 lines JSON")
    cleaned = []
    for item in lines:
        if not isinstance(item, dict):
            continue
        source = lyric_source_key(item.get("source") or "")
        units = []
        for unit in item.get("units") or []:
            if not isinstance(unit, dict):
                continue
            try:
                unit_model = LyricToken.model_validate(unit)
            except Exception:
                continue
            sing = lyric_source_key(unit_model.surface)
            if not sing or _INDEX_UNIT.fullmatch(sing):
                continue
            pronunciation = unit_model.pronunciation
            pronunciation_value = (
                str(pronunciation.value or "").strip()
                if hasattr(pronunciation, "value")
                else str(pronunciation.get("value") or "").strip()
                if isinstance(pronunciation, dict)
                else ""
            )
            reading = unit_model.reading or str(unit.get("label") or "").strip()
            romaji = unit_model.romaji or pronunciation_value
            translation = unit_model.translation
            units.append(
                restore_romaji_unit(
                    source=source,
                    unit={
                        "sing": sing,
                        "surface": sing,
                        "label": reading,
                        "reading": reading,
                        "romaji": romaji,
                        "pronunciation": {"system": "romaji", "value": romaji}
                        if romaji
                        else {},
                        "zh": translation,
                        "translation": translation,
                    },
                )
            )
        line_zh = str(item.get("translation") or item.get("zh") or "").strip()
        if source and (units or line_zh):
            cleaned.append(
                {
                    "source": source,
                    "zh": line_zh,
                    "translation": line_zh,
                    "units": units,
                }
            )
    if not cleaned:
        raise ValueError("agent 没有可用的注音行")
    return {"lines": cleaned}


def complete_json(
    messages: list[dict[str, str]], model: str | None = None
) -> dict[str, Any]:
    base = agent_base_url()
    key = agent_api_key()
    if not base or not key:
        raise RuntimeError("日语注音 agent 未配置 LOVKTV_AGENT_URL/OPENAI_BASE_URL")
    body = {
        "model": model or agent_model(),
        "temperature": 0.1,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    url = f"{base}/chat/completions"
    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(url, headers=headers, json=body)
    except Exception as exc:
        if "socksio" not in str(exc):
            raise
        with httpx.Client(timeout=180.0, trust_env=False) as client:
            response = client.post(url, headers=headers, json=body)
    response.raise_for_status()
    data = response.json()
    if (
        isinstance(data, dict)
        and data.get("choices") is None
        and isinstance(data.get("data"), dict)
    ):
        if data.get("code") not in (None, 0, 200):
            raise RuntimeError(str(data.get("msg") or "agent 请求失败"))
        data = data["data"]
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text") or "" if isinstance(part, dict) else str(part)
            for part in content
        )
    if not content:
        raise RuntimeError(str(data.get("msg") or "agent 没有返回内容"))
    return _parse_payload(str(content))


def _request_chunk(lines: list[str], title: str, artist: str) -> list[dict[str, Any]]:
    numbered = "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))
    user = (
        f"Song: {title} / {artist}\n"
        "Annotate every line below. Read the batch as surrounding lyric context when choosing readings and Chinese meanings; keep source exactly the same. The faithful, clear whole-line Chinese meaning takes priority over literal unit glosses.\n\n"
        f"{numbered}"
    )
    payload = complete_json(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ]
    )
    return list(payload["lines"])


def annotate_ja_lines(
    lines: list[str],
    title: str = "",
    artist: str = "",
    cache_path: Path | None = None,
    chunk_size: int = 24,
    force: bool = False,
) -> dict[str, Any]:
    texts = [str(line or "") for line in lines]
    digest = _source_hash(texts, title, artist)
    if cache_path and cache_path.exists() and not force:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = {}
        if (
            cached.get("source_hash") == digest
            and cached.get("schema") == ANNOTATION_SCHEMA
            and cached.get("lines")
        ):
            return cached
    if not agent_enabled():
        raise RuntimeError("日语注音 agent 未启用")
    collected: list[dict[str, Any]] = []
    unique: list[str] = []
    seen: set[str] = set()
    for line in texts:
        if line and line not in seen:
            unique.append(line)
            seen.add(line)
    for start in range(0, len(unique), chunk_size):
        collected.extend(
            _request_chunk(unique[start : start + chunk_size], title, artist)
        )
    result = {
        "schema": ANNOTATION_SCHEMA,
        "source_hash": digest,
        "model": agent_model(),
        "title": title,
        "artist": artist,
        "lines": collected,
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


def lyric_source_key(text: str) -> str:
    """Agent often echoes '1. 原文'; match the lyric line without that prefix."""
    return _LINE_NO.sub(
        "", unicodedata.normalize("NFKC", str(text or "")), count=1
    ).strip()


def _clean_label(label: str) -> str:
    raw = unicodedata.normalize("NFKC", str(label or "")).strip()
    if not raw:
        return ""
    if (
        re.search(r"[A-Za-zÀ-ÿ]", raw)
        and not _KANJI.search(raw)
        and not _HIRA.search(raw)
    ):
        return raw
    hira = "".join(char for char in raw if _HIRA.match(char) or char == "ー")
    kanji = "".join(char for char in raw if _KANJI.match(char))
    if hira and not kanji:
        return hira
    if kanji:
        return kanji
    return ""


def _latin_label(label: str) -> str:
    raw = unicodedata.normalize("NFKC", str(label or "")).strip()
    return raw if re.search(r"[A-Za-zÀ-ÿ]", raw) and not _KANJI.search(raw) else ""


def _sung_kana(specs: list[tuple[str, str]]) -> str:
    bits: list[str] = []
    for piece, reading in specs:
        if reading and not _KANJI.search(reading):
            bits.append(reading)
        else:
            bits.append(piece)
    return _kana_key("".join(bits))


def _flip_kanji_specs(snippet: str, sing: str) -> list[tuple[str, str]] | None:
    from lovktv.pipeline.lyrics import ja_token_specs

    if not snippet:
        return None
    leftover = _merge_plain_kana(ja_token_specs(snippet))
    if leftover and _sung_kana(leftover) == _kana_key(sing):
        return leftover
    return None


def _join_surfaces(parts: list[str]) -> str:
    out: list[str] = []
    for piece in parts:
        if not piece:
            continue
        if (
            out
            and re.match(r"[A-Za-z0-9']", piece)
            and re.search(r"[A-Za-z0-9']$", out[-1] or "")
        ):
            out.append(" ")
        out.append(piece)
    return "".join(out)


def _source_span_for_kanji(source: str, kanji: str) -> str:
    """Slice of the original line covering these kanji, plus following okurigana."""
    if not source or not kanji:
        return ""
    start: int | None = None
    matched = 0
    for index, char in enumerate(source):
        if matched < len(kanji) and char == kanji[matched]:
            if start is None:
                start = index
            matched += 1
            if matched == len(kanji):
                end = index + 1
                while end < len(source) and _HIRA.match(source[end]):
                    end += 1
                return source[start:end]
    return ""


def _kana_key(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKC", text or "") if not char.isspace()
    )


def _merge_plain_kana(specs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for piece, label in specs:
        if (
            merged
            and not label
            and not merged[-1][1]
            and _KANA.search(piece)
            and not _KANJI.search(piece)
            and _KANA.search(merged[-1][0])
            and not _KANJI.search(merged[-1][0])
        ):
            merged[-1] = (merged[-1][0] + piece, "")
            continue
        merged.append((piece, label))
    return merged


def _units_cover_romaji(units: list[dict[str, str]], source: str) -> bool:
    words = _LATIN_WORD.findall(source)
    if len(words) < 3:
        return True
    covered: list[str] = []
    for unit in units:
        roma = str(unit.get("romaji") or "").strip()
        sing = lyric_source_key(unit.get("sing") or "")
        if roma:
            covered.extend(_LATIN_WORD.findall(roma))
        elif (
            _LATIN_WORD.search(sing)
            and not _KANA.search(sing)
            and not _KANJI.search(sing)
        ):
            covered.extend(_LATIN_WORD.findall(sing))
    return len(covered) >= max(2, int(len(words) * 0.7))


def expand_units(
    units: list[dict[str, str]], source: str = ""
) -> list[tuple[str, str]]:
    from lovktv.pipeline.lyrics import ja_token_specs

    specs: list[tuple[str, str]] = []
    source = unicodedata.normalize("NFKC", source or "")
    for unit in units:
        sing = lyric_source_key(unit.get("sing") or "")
        raw_label = unicodedata.normalize("NFKC", unit.get("label") or "")
        label = _clean_label(raw_label)
        if not sing.strip() or _INDEX_UNIT.fullmatch(sing.strip()):
            continue
        if (
            re.search(r"[A-Za-z]", sing)
            and not _KANJI.search(sing)
            and not _KANA.search(sing)
        ):
            parts = [part for part in _LATIN_PART.findall(sing) if part.strip()]
            english = _latin_label(label)
            for part in parts:
                specs.append((part, english if len(parts) == 1 else ""))
            continue
        surface = "".join(char for char in sing if not char.isspace())
        kanji_only = "".join(char for char in raw_label if _KANJI.match(char))
        romaji = str(unit.get("romaji") or "").strip()
        # Newer agent responses already use the sung Japanese surface in
        # ``sing`` and put its complete reading in ``label``. Keep that
        # semantic unit intact: splitting ``もう一度`` into ``もう`` + ``一度``
        # would leave the unit's single ``mou ichido`` romaji under the first
        # token, making the following token appear untranslated. The legacy
        # kana-sing/kanji-label format is handled by the branches above.
        if _KANJI.search(surface) and _HIRA.search(label) and not _KANJI.search(label):
            specs.append((surface, label))
            continue
        # Some cached agent responses use a short kanji label (for example
        # ``お宝 / 宝``) while ``sing`` still contains the complete surface.
        # A supplied romaji and gloss identify this as one semantic unit, so
        # do not let pykakasi split the surface and strand the annotation on
        # its first character.
        if _KANJI.search(surface) and romaji and (label or raw_label):
            specs.append((surface, label if _HIRA.search(label) else ""))
            continue
        if _KANJI.search(sing):
            leftover = _merge_plain_kana(ja_token_specs(sing))
            if leftover:
                if (
                    label
                    and _HIRA.search(label)
                    and not _KANJI.search(label)
                    and len(leftover) == 1
                ):
                    specs.append((leftover[0][0], label))
                else:
                    specs.extend(leftover)
                continue
        if kanji_only:
            # Legacy responses may put a complete word such as
            # ``きえる / 消える`` in one unit. When the source is romaji,
            # preserve that one-to-one unit instead of letting pykakasi split
            # the okurigana into ``消え`` + ``る`` and leaving the unit's
            # ``kieru`` romaji on only the first piece.
            if (
                _HIRA.search(raw_label)
                and len(_KANJI_RUN.findall(raw_label)) == 1
                and not _KANJI.search(source)
            ):
                specs.append((raw_label, surface))
                continue
            snippet = (
                raw_label
                if _HIRA.search(raw_label)
                else _source_span_for_kanji(source, kanji_only)
            )
            flipped = _flip_kanji_specs(snippet, surface)
            if flipped:
                specs.extend(flipped)
                continue
            display = snippet or raw_label or kanji_only
            specs.append((display if _KANJI.search(display) else kanji_only, surface))
            continue
        if _is_katakana(surface):
            specs.append((surface, _latin_label(label)))
            continue
        if _latin_label(label) or romaji:
            specs.append((surface, _latin_label(label)))
            continue
        for char in surface:
            specs.append((char, ""))
    return specs


def _romaji_for_piece(piece: str, fallback: str, index: int, total: int) -> str:
    """Return romaji belonging to one rendered token when the note is split.

    A Japanese semantic word can legitimately render as several kana/kanji
    pieces (for example an okurigana split).  Preserve its whole-word romaji
    on the first piece; only distribute it when the agent explicitly supplied
    separate whitespace-delimited readings.
    """
    if total <= 1:
        return fallback
    parts = [part for part in re.split(r"\s+", fallback.strip()) if part]
    if len(parts) == total:
        return parts[index]
    return fallback if index == 0 else ""


def apply_ja_annotation(
    timeline: dict[str, Any], notes: dict[str, Any]
) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    for item in notes.get("lines") or []:
        source = lyric_source_key(item.get("source") or "")
        units = [
            unit
            for unit in item.get("units") or []
            if isinstance(unit, dict) and (unit.get("surface") or unit.get("sing"))
        ]
        if source and units:
            by_source[source] = item
    for cue in timeline.get("cues") or []:
        text = lyric_source_key(cue.get("text") or "")
        original = lyric_source_key(cue.get("source_text") or text)
        item = by_source.get(original) or by_source.get(text)
        if not item:
            continue
        # Cached notes may still carry the agent's ``surface=romaji /
        # reading=kana`` mistake; normalize before expanding so a plain
        # ``--reapply`` restores the Japanese without another agent call.
        units = [
            restore_romaji_unit(unit, source=original)
            for unit in item.get("units") or []
            if isinstance(unit, dict) and (unit.get("surface") or unit.get("sing"))
        ]
        line_zh = valid_zh(item.get("translation") or item.get("zh") or "")
        if line_zh:
            cue["zh"] = line_zh
            cue["translation"] = line_zh
        elif not valid_zh(cue.get("zh") or cue.get("translation") or ""):
            cue.pop("zh", None)
            cue.pop("translation", None)
        specs: list[tuple[str, str, str, str]] = []
        for unit in units:
            roma = _unit_romaji_text(unit)
            gloss = valid_zh(unit.get("translation") or unit.get("zh") or "")
            normalized_unit = {
                **unit,
                "sing": unit.get("surface") or unit.get("sing") or "",
                "label": unit.get("reading") or unit.get("label") or "",
            }
            pieces = expand_units([normalized_unit], source=original)
            for index, (piece, label) in enumerate(pieces):
                piece_romaji = _romaji_for_piece(piece, roma, index, len(pieces))
                specs.append(
                    (
                        piece,
                        label,
                        piece_romaji,
                        gloss if index == 0 else "",
                    )
                )
        if not specs:
            continue
        japanese = japanese_from_units(
            [
                {**unit, "sing": unit.get("surface") or unit.get("sing") or ""}
                for unit in units
            ]
        )
        displayed = _join_surfaces([piece for piece, _label, _roma, _gloss in specs])
        current = lyric_source_key(cue.get("text") or "")
        # ``normalize_timeline`` prefers ``surface`` over ``text``; keep both
        # in step or the restored kana silently reverts to romaji on save.
        if line_is_romaji(original) and not _units_cover_romaji(units, original):
            if line_is_romaji(current):
                continue
            if japanese and japanese == current:
                cue["text"] = original
                cue["surface"] = original
                continue
        # A few legacy cues contain confusable Latin characters (such as
        # Cyrillic ``е``), so ``line_is_romaji`` is not sufficient here.  If
        # the annotation produced Japanese and the cue surface has no
        # Japanese script, always replace the rendered text with kana/kanji.
        if (displayed or japanese) and not _JA_SCRIPT.search(current):
            cue["source_text"] = original
            cue["text"] = displayed or japanese
            cue["surface"] = cue["text"]
        start_ms = int(cue["start_ms"])
        end_ms = int(cue.get("sing_end_ms") or cue["end_ms"])
        span = max(end_ms - start_ms, 200)
        unit_ms = span / len(specs)
        tokens = []
        cursor = start_ms
        for index, (piece, label, roma, gloss) in enumerate(specs):
            token_end = end_ms if index == len(specs) - 1 else int(cursor + unit_ms)
            token = {
                "text": piece,
                "surface": piece,
                "start_ms": int(cursor),
                "end_ms": int(max(cursor + 40, token_end)),
                "reading": label,
                "romaji": roma,
                "translation": gloss,
            }
            if gloss:
                token["zh"] = gloss
            if roma:
                token["pronunciation"] = {"system": "romaji", "value": roma}
            tokens.append(token)
            cursor = token_end
        tokens[-1]["end_ms"] = end_ms
        cue["tokens"] = tokens
    timeline["annotation"] = "ja-agent"
    timeline["annotation_model"] = str(notes.get("model") or agent_model())
    return timeline
