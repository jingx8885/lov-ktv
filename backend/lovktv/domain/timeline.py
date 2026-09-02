"""Runtime guards for persisted lyric timelines."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

LYRICS_SCHEMA = "lovktv-lyrics-v2"


class LyricPronunciation(BaseModel):
    model_config = ConfigDict(extra="allow")

    system: str = ""
    value: str = ""


class LyricToken(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str = ""
    surface: str = ""
    start_ms: int = 0
    end_ms: int = 0
    reading: str = ""
    romaji: str = ""
    translation: str = ""
    zh: str = ""
    pronunciation: LyricPronunciation | dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def aliases(cls, value: Any) -> Any:
        data = dict(value or {})
        surface = str(data.get("surface") or data.get("text") or data.get("sing") or "").strip()
        translation = str(data.get("translation") or data.get("zh") or "").strip()
        data["surface"] = surface
        data["text"] = surface
        data["translation"] = translation
        data["zh"] = translation
        pronunciation = data.get("pronunciation")
        romaji = str(data.get("romaji") or "").strip()
        if not isinstance(pronunciation, dict) or not pronunciation.get("value"):
            data["pronunciation"] = {"system": "romaji", "value": romaji} if romaji else {}
        return data


class LyricCue(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str = ""
    surface: str = ""
    start_ms: int = 0
    end_ms: int = 0
    translation: str = ""
    zh: str = ""
    tokens: list[LyricToken] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def aliases(cls, value: Any) -> Any:
        data = dict(value or {})
        surface = str(data.get("surface") or data.get("text") or "").strip()
        translation = str(data.get("translation") or data.get("zh") or "").strip()
        data["surface"] = surface
        data["text"] = surface
        data["translation"] = translation
        data["zh"] = translation
        return data


class LyricsTimeline(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_: str = Field(default=LYRICS_SCHEMA, alias="schema")
    cues: list[LyricCue] = Field(default_factory=list)


def _normalize_token(raw: dict[str, Any], start: int, end: int) -> dict[str, Any] | None:
    token_model = LyricToken.model_validate(raw)
    surface = token_model.surface
    if not surface:
        return None
    token = token_model.model_dump(mode="json")
    token["start_ms"] = max(start, int(token_model.start_ms or start))
    token["end_ms"] = max(token["start_ms"], min(end, int(token_model.end_ms or end)))
    return token


def normalize_timeline(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("cues"), list):
        raise ValueError("歌词时间轴无效")
    try:
        timeline_model = LyricsTimeline.model_validate(payload)
    except Exception as exc:
        raise ValueError("歌词时间轴无效") from exc
    cues: list[dict[str, Any]] = []
    for raw_model in timeline_model.cues:
        raw = raw_model.model_dump(mode="json")
        if not raw_model.surface:
            continue
        start = max(0, int(raw_model.start_ms or 0))
        end = max(start + 1, int(raw_model.end_ms or 0))
        cue = dict(raw)
        text = raw_model.surface
        translation = raw_model.translation
        cue.update(
            text=text,
            surface=text,
            translation=translation,
            zh=translation,
            start_ms=start,
            end_ms=end,
        )
        tokens: list[dict[str, Any]] = []
        for token_model in raw_model.tokens:
            token_data = _normalize_token(token_model.model_dump(mode="json"), start, end)
            if token_data:
                tokens.append(token_data)
        cue["tokens"] = tokens
        cues.append(cue)
    if not cues:
        raise ValueError("歌词时间轴无效")
    cues.sort(key=lambda cue: (cue["start_ms"], cue["end_ms"]))
    return {**payload, "schema": LYRICS_SCHEMA, "cues": cues}
