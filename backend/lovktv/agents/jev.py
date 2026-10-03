"""Jev (System One) decision client: fast typed judgments, never text.

Contract (same as lov-evo internal/jev): POST {base}/systemone on the
shared new-api gateway with one structured state plus typed questions;
the response carries calibrated answers.

    questions = {
        "zh_ok": {"type": "noul", "instructions": "Is zh faithful to line 1?"},
        "kind":  {"type": "choice", "instructions": "...", "criteria": {"a": "..."}},
        "how":   {"type": "score", "instructions": "...", "levels": ["low", "high"]},
    }

Jev only judges. It does not write lyrics, translations, or readings;
callers branch on the answers and keep generation on the LLM agents.
All helpers fail open: a Jev outage must never block the lyric pipeline.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

_DEFAULT_MODEL = "jev-latest"
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504, 529}
_ATTEMPTS = 3
_MAX_ERROR_BODY = 2048


class JevError(RuntimeError):
    """Gateway or protocol failure talking to System One."""


@dataclass
class Question:
    """One typed question. type is noul | choice | score."""

    type: str
    instructions: str
    # choice: {option: description}; noul: optional extra criteria map.
    criteria: dict[str, Any] | None = None
    # score: ordered level labels, 2-10 entries.
    levels: list[str] | None = None


@dataclass
class EvalResult:
    model: str = ""
    answers: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def jev_base_url() -> str:
    from lovktv.agents.ja_lyrics import agent_base_url

    return agent_base_url()


def jev_api_key() -> str:
    from lovktv.agents.ja_lyrics import agent_api_key

    return agent_api_key()


def jev_model() -> str:
    return (os.environ.get("LOVKTV_JEV_MODEL") or _DEFAULT_MODEL).strip()


def jev_timeout() -> httpx.Timeout:
    raw = os.environ.get("LOVKTV_JEV_TIMEOUT")
    try:
        read = float(raw) if raw else 30.0
    except (TypeError, ValueError):
        read = 30.0
    return httpx.Timeout(connect=10.0, read=max(5.0, read), write=30.0, pool=10.0)


def _marshal_questions(questions: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for qid, question in questions.items():
        q = question if isinstance(question, Question) else Question(**question)
        item: dict[str, Any] = {"type": q.type, "instructions": q.instructions}
        if q.type == "noul":
            if q.criteria:
                item["criteria"] = q.criteria
        elif q.type == "choice":
            if not q.criteria:
                raise JevError(f"question {qid}: choice needs criteria options")
            item["criteria"] = q.criteria
        elif q.type == "score":
            if not q.levels or not 2 <= len(q.levels) <= 10:
                raise JevError(f"question {qid}: score needs 2-10 levels")
            item["criteria"] = list(q.levels)
        else:
            raise JevError(f"question {qid}: unknown type {q.type!r}")
        out[qid] = item
    return out


def noul_value(answer: Any) -> float | None:
    """Yes-probability of a noul answer, or None when missing."""
    if not isinstance(answer, dict):
        return None
    value = answer.get("noul")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def evaluate(
    state: Any,
    questions: dict[str, Any],
    *,
    client: Any = None,
) -> EvalResult:
    """One judgment request; returns all answers. Raises JevError."""
    if not questions:
        raise JevError("questions must be non-empty")
    base = jev_base_url()
    key = jev_api_key()
    if not base or not key:
        raise JevError("jev 未配置 agent_url/agent_key")
    body = json.dumps(
        {"model": jev_model(), "state": state, "questions": _marshal_questions(questions)},
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    url = base + "/systemone"
    last = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            if client is not None:
                response = client.post(url, headers=headers, content=body)
            else:
                with httpx.Client(timeout=jev_timeout()) as hc:
                    response = hc.post(url, headers=headers, content=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = JevError(f"systemone request failed: {exc}")
            if attempt < _ATTEMPTS:
                time.sleep(0.6 * attempt)
            continue
        code = response.status_code
        if code in (401, 403):
            raise JevError("systemone auth failed HTTP " + str(code))
        if code in _RETRYABLE_STATUS or code >= 500:
            last = JevError(f"systemone HTTP {code}: {response.text[:_MAX_ERROR_BODY]}")
            if attempt < _ATTEMPTS:
                time.sleep(0.6 * attempt)
            continue
        if code < 200 or code >= 300:
            raise JevError(f"systemone HTTP {code}: {response.text[:_MAX_ERROR_BODY]}")
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            last = JevError(f"systemone response is not JSON: {exc}")
            if attempt < _ATTEMPTS:
                time.sleep(0.6 * attempt)
            continue
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, dict):
            raise JevError("systemone response has no answers")
        missing = [qid for qid in questions if qid not in answers]
        if missing:
            raise JevError(f"systemone response missing answers: {missing}")
        return EvalResult(
            model=str(data.get("model") or ""),
            answers=answers,
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else {},
        )
    raise last if isinstance(last, JevError) else JevError(str(last))


def try_evaluate(
    state: Any,
    questions: dict[str, Any],
    *,
    client: Any = None,
) -> EvalResult:
    """Fail-open variant: errors land in result.error instead of raising."""
    try:
        return evaluate(state, questions, client=client)
    except Exception as exc:  # noqa: BLE001 - judgment must never block the caller
        return EvalResult(error=str(exc))

