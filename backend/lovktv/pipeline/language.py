from __future__ import annotations

import re

_HIRAGANA = re.compile(r"[\u3040-\u309f]")
_KATAKANA = re.compile(r"[\u30a0-\u30ff]")
_HAN = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_YUE_MARK = re.compile(r"[嘅咗喺冇佢哋唔嗰啲咁嚟嘢咪喎啦嘞]")
_YUE_HINTS = {
    "yue",
    "cantonese",
    "粤语",
    "粵語",
    "广东话",
    "廣東話",
    "粤",
    "粵",
}
WHISPER_LANGS = {"zh", "ja", "en", "yue"}
CJK_LANGS = {"zh", "ja", "yue"}


def whisper_language(language: str | None) -> str:
    lang = (language or "").strip().lower()
    return lang if lang in WHISPER_LANGS else "zh"


def detect_language(text: str, hint: str | None = None) -> str:
    raw_hint = str(hint or "").strip()
    hint_key = raw_hint.lower()
    ja = bool(_HIRAGANA.search(text) or _KATAKANA.search(text))
    if ja:
        return "ja"
    if hint_key in _YUE_HINTS or raw_hint in _YUE_HINTS:
        return "yue"
    has_han = bool(_HAN.search(text))
    has_latin = bool(_LATIN.search(text))
    if has_han and len(set(_YUE_MARK.findall(text))) >= 2:
        return "yue"
    if has_han and not has_latin:
        return "zh"
    if has_latin and not has_han:
        return "en"
    if hint_key in WHISPER_LANGS:
        return hint_key
    if has_han:
        return "zh"
    if has_latin:
        return "en"
    return "zh"
