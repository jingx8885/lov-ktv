"""Versioned contract for the lyric/ASR alignment agent.

The agent is allowed to reason about missing audio, but it is not allowed to
silently drop a source lyric line.  This module is deliberately independent
from the Pi runtime so both a Python agent adapter and a future Node sidecar
can validate the same JSON document.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ALIGNMENT_SCHEMA = "lovktv-agent-alignment-v1"
AlignmentStatus = Literal["matched", "uncertain", "inferred", "absent"]


class AlignmentRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    lyric: int = Field(ge=1)
    status: AlignmentStatus
    from_: int | None = Field(default=None, alias="from", ge=1)
    to: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = ""

    @model_validator(mode="after")
    def check_span(self) -> "AlignmentRow":
        if self.status in {"matched", "uncertain"}:
            if self.from_ is None or self.to is None:
                raise ValueError("matched/uncertain rows require from and to")
            if self.from_ > self.to:
                raise ValueError("alignment span is reversed")
        elif self.from_ is not None or self.to is not None:
            raise ValueError("inferred/absent rows cannot claim ASR words")
        if self.status in {"inferred", "absent"} and not self.reason.strip():
            raise ValueError("inferred/absent rows require a reason")
        return self


class AlignmentGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_lyric: int = Field(ge=1, alias="from_lyric")
    to_lyric: int = Field(ge=1, alias="to_lyric")
    status: Literal["inferred_group", "absent_group"]
    reason: str = ""

    @model_validator(mode="after")
    def check_range(self) -> "AlignmentGroup":
        if self.from_lyric > self.to_lyric:
            raise ValueError("alignment group is reversed")
        if not self.reason.strip():
            raise ValueError("alignment group requires a reason")
        return self


class AgentAlignment(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_: str = Field(default=ALIGNMENT_SCHEMA, alias="schema")
    rows: list[AlignmentRow]
    groups: list[AlignmentGroup] = Field(default_factory=list)
    trace_id: str = ""

    @model_validator(mode="after")
    def unique_lyrics(self) -> "AgentAlignment":
        ids = [row.lyric for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("each lyric line must appear exactly once")
        return self

    def legacy_matches(self) -> list[dict[str, int]]:
        """Return the old matcher shape for the existing orchestrator."""
        return [
            {"lyric": row.lyric, "from": row.from_, "to": row.to}
            for row in self.rows
            if row.status in {"matched", "uncertain"}
            and row.from_ is not None
            and row.to is not None
        ]


class GeneratedLyricToken(BaseModel):
    """One source-language unit emitted by the generation agent."""

    model_config = ConfigDict(extra="allow")

    surface: str = ""
    translation: str = ""
    reading: str = ""
    romaji: str = ""
    pronunciation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def aliases(cls, value: Any) -> Any:
        data = dict(value or {})
        surface = str(data.get("surface") or data.get("text") or data.get("sing") or "").strip()
        translation = str(data.get("translation") or data.get("zh") or "").strip()
        data["surface"] = surface
        data["translation"] = translation
        return data

    @model_validator(mode="after")
    def require_surface(self) -> "GeneratedLyricToken":
        if not self.surface.strip():
            raise ValueError("generated token requires surface")
        if not self.translation.strip():
            raise ValueError("generated token requires translation")
        return self


class GeneratedLyricRow(BaseModel):
    """Complete line result: timing anchor plus token-level display data."""

    model_config = ConfigDict(extra="allow")

    lyric: int = Field(ge=1)
    status: AlignmentStatus
    text: str = ""
    translation: str = ""
    from_: int | None = Field(default=None, alias="from", ge=1)
    to: int | None = Field(default=None, ge=1)
    tokens: list[GeneratedLyricToken] = Field(default_factory=list)
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def aliases(cls, value: Any) -> Any:
        data = dict(value or {})
        data["text"] = str(data.get("text") or data.get("source") or "").strip()
        data["translation"] = str(data.get("translation") or data.get("zh") or "").strip()
        return data

    @model_validator(mode="after")
    def validate_row(self) -> "GeneratedLyricRow":
        if not self.text.strip():
            raise ValueError("generated lyric row requires text")
        if not self.translation.strip():
            raise ValueError("generated lyric row requires translation")
        if not self.tokens:
            raise ValueError("generated lyric row requires token-level decomposition")
        source = _compact(self.text)
        covered = _compact("".join(token.surface for token in self.tokens))
        if source != covered:
            raise ValueError("generated tokens do not cover the source lyric exactly")
        if self.status in {"matched", "uncertain"}:
            if self.from_ is None or self.to is None or self.from_ > self.to:
                raise ValueError("matched/uncertain generated row requires valid span")
        elif self.from_ is not None or self.to is not None:
            raise ValueError("inferred/absent generated row cannot claim ASR span")
        if self.status in {"inferred", "absent"} and not self.reason.strip():
            raise ValueError("inferred/absent generated row requires reason")
        return self


class GeneratedLyrics(BaseModel):
    """Pi's direct-generation response, validated before timeline writing."""

    model_config = ConfigDict(extra="allow")

    schema_: str = Field(default="lovktv-generated-lyrics-v1", alias="schema")
    language: str = ""
    rows: list[GeneratedLyricRow]
    groups: list[AlignmentGroup] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_rows(self) -> "GeneratedLyrics":
        ids = [row.lyric for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("each lyric line must appear exactly once")
        return self

    def legacy_matches(self) -> list[dict[str, int]]:
        """Expose timing anchors for the existing timeline builder."""
        return [
            {"lyric": row.lyric, "from": row.from_, "to": row.to}
            for row in self.rows
            if row.status in {"matched", "uncertain"}
            and row.from_ is not None
            and row.to is not None
        ]


def parse_generated_lyrics(
    payload: Any,
    *,
    lyric_count: int | None = None,
    expected_lyrics: set[int] | None = None,
    word_count: int | None = None,
) -> GeneratedLyrics:
    """Validate a direct-generation response and its ASR references."""
    result = GeneratedLyrics.model_validate(payload)
    if expected_lyrics is not None or lyric_count is not None:
        expected = expected_lyrics if expected_lyrics is not None else set(range(1, lyric_count + 1))
        actual = {row.lyric for row in result.rows}
        if actual != expected:
            raise ValueError(
                f"generated lyrics must account for every line; missing={sorted(expected - actual)}"
            )
    used: set[int] = set()
    for row in result.rows:
        if row.from_ is None or row.to is None:
            continue
        if word_count is not None and row.to > word_count:
            raise ValueError("generated lyrics reference an ASR word outside the transcript")
        overlap = used.intersection(range(row.from_, row.to + 1))
        if overlap:
            raise ValueError(f"ASR words reused: {sorted(overlap)}")
        used.update(range(row.from_, row.to + 1))
    return result


def _compact(value: str) -> str:
    """Normalize only whitespace for exact source/token coverage checks."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or ""))


def parse_alignment_payload(
    payload: Any,
    *,
    lyric_count: int | None = None,
    word_count: int | None = None,
) -> AgentAlignment:
    """Parse new protocol JSON and accept the previous matches/missing form."""
    if not isinstance(payload, dict):
        raise ValueError("alignment payload must be an object")
    if isinstance(payload.get("rows"), list):
        result = AgentAlignment.model_validate(payload)
    else:
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise ValueError("alignment payload has no rows or matches")
        rows: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in matches:
            if not isinstance(item, dict):
                continue
            try:
                lyric = int(item["lyric"])
                start = int(item["from"])
                end = int(item["to"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append({"lyric": lyric, "status": "matched", "from": start, "to": end})
            seen.add(lyric)
        missing = payload.get("missing") or []
        for lyric in missing if isinstance(missing, list) else []:
            try:
                number = int(lyric)
            except (TypeError, ValueError):
                continue
            if number not in seen:
                rows.append({"lyric": number, "status": "absent", "reason": "legacy agent marked missing"})
                seen.add(number)
        result = AgentAlignment.model_validate({"rows": rows, "groups": []})
    if lyric_count is not None:
        expected = set(range(1, lyric_count + 1))
        actual = {row.lyric for row in result.rows}
        if actual != expected:
            raise ValueError(f"alignment must account for every lyric line; missing={sorted(expected - actual)}")
    used: set[int] = set()
    for row in result.rows:
        if row.from_ is None or row.to is None:
            continue
        if word_count is not None and row.to > word_count:
            raise ValueError("alignment references an ASR word outside the transcript")
        overlap = used.intersection(range(row.from_, row.to + 1))
        if overlap:
            raise ValueError(f"ASR words reused: {sorted(overlap)}")
        used.update(range(row.from_, row.to + 1))
    return result
