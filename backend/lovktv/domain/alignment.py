"""Versioned contract for the sung-lyrics generation agent.

The agent receives the ASR transcript (with word timestamps) as the record of
what was actually sung, plus the reference lyrics as a spelling/context aid.
It returns the sung lines in time order.  Timing stays server-owned: every
millisecond in the final timeline is derived from ASR word spans or
interpolated between them, never taken from the model.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUNG_SCHEMA = "lovktv-sung-lyrics-v1"
SungStatus = Literal["matched", "inferred"]


class SungToken(BaseModel):
    """One display unit of a sung line with optional glosses."""

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
        data["surface"] = str(data.get("surface") or data.get("text") or "").strip()
        data["translation"] = str(data.get("translation") or data.get("zh") or "").strip()
        return data

    @model_validator(mode="after")
    def require_surface(self) -> "SungToken":
        if not self.surface:
            raise ValueError("token requires surface")
        return self


class SungLine(BaseModel):
    """One line as actually sung, anchored to a 1-based inclusive ASR word span.

    ``matched`` rows own an ASR span.  ``inferred`` rows are lines the model is
    confident were sung (from reference context) but the transcript missed;
    they carry no span and are placed between their neighbours by the server.
    """

    model_config = ConfigDict(extra="allow")

    text: str = ""
    status: SungStatus = "matched"
    from_: int | None = Field(default=None, alias="from", ge=1)
    to: int | None = Field(default=None, ge=1)
    ref: int | None = Field(default=None, ge=1)
    translation: str = ""
    tokens: list[SungToken] = Field(default_factory=list)
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def aliases(cls, value: Any) -> Any:
        data = dict(value or {})
        data["text"] = str(data.get("text") or data.get("line") or "").strip()
        data["translation"] = str(data.get("translation") or data.get("zh") or "").strip()
        if data.get("status") not in ("matched", "inferred"):
            data["status"] = "matched" if data.get("from") is not None else "inferred"
        return data

    @model_validator(mode="after")
    def check_span(self) -> "SungLine":
        if not self.text:
            raise ValueError("sung line requires text")
        if self.status == "matched":
            if self.from_ is None or self.to is None:
                raise ValueError("matched line requires from/to")
            if self.from_ > self.to:
                raise ValueError("sung line span is reversed")
        elif self.from_ is not None or self.to is not None:
            raise ValueError("inferred line cannot claim ASR words")
        return self


class SungLyrics(BaseModel):
    """Validated generation response: sung lines in transcript order."""

    model_config = ConfigDict(extra="allow")

    schema_: str = Field(default=SUNG_SCHEMA, alias="schema")
    language: str = ""
    rows: list[SungLine]

    @model_validator(mode="after")
    def order_rows(self) -> "SungLyrics":
        # Matched rows must not share words and must be strictly ascending;
        # inferred rows keep their relative position among neighbours.
        last_to = 0
        for row in self.rows:
            if row.from_ is None or row.to is None:
                continue
            if row.from_ <= last_to:
                raise ValueError("sung lines overlap or run backwards in ASR order")
            last_to = row.to
        return self


def parse_sung_lyrics(payload: Any, *, word_count: int | None = None) -> SungLyrics:
    """Validate a generation response against the transcript it was given."""
    if not isinstance(payload, dict):
        raise ValueError("sung lyrics payload must be an object")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("sung lyrics payload has no rows")
    if word_count is not None:
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("to"), int) and row["to"] > word_count:
                raise ValueError("sung line references an ASR word outside the transcript")
    result = SungLyrics.model_validate(payload)
    if not result.rows:
        raise ValueError("sung lyrics payload has no lines")
    if not any(row.status == "matched" for row in result.rows):
        raise ValueError("sung lyrics need at least one line anchored to ASR words")
    return result
