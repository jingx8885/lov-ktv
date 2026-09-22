import json

import httpx
import pytest

from lovktv.agents import alignment, ja_lyrics
from lovktv.agents.ja_lyrics import AgentUnavailable


def _response(status: int, content: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": content}}]},
        request=httpx.Request("POST", "http://agent.example/v1/chat/completions"),
    )


def _install(monkeypatch, script: list):
    calls: list[dict] = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            calls.append(json)
            action = script.pop(0)
            if isinstance(action, Exception):
                raise action
            return action

    monkeypatch.setattr(ja_lyrics.httpx, "Client", Client)
    monkeypatch.setattr(ja_lyrics, "agent_model", lambda: "gpt-5.6-luna")
    monkeypatch.setattr(ja_lyrics, "agent_base_url", lambda: "http://agent.example/v1")
    monkeypatch.setattr(ja_lyrics, "agent_api_key", lambda: "test-key")
    monkeypatch.setenv("LOVKTV_AGENT_RETRY_DELAY", "0")
    monkeypatch.setenv("LOVKTV_AGENT_FALLBACK_MODEL", "grok-4.6")
    ja_lyrics.reset_agent_models_used()
    return calls


def test_primary_model_is_used_when_luna_answers(monkeypatch):
    calls = _install(monkeypatch, [_response(200, "ok")])
    text = ja_lyrics.post_chat([{"role": "user", "content": "hi"}], temperature=0.1)
    assert text == "ok"
    assert [item["model"] for item in calls] == ["gpt-5.6-luna"]
    assert calls[0]["temperature"] == 0.1
    assert ja_lyrics.agent_model_used() == "gpt-5.6-luna"


def test_luna_is_retried_before_switching_models(monkeypatch):
    calls = _install(
        monkeypatch,
        [httpx.TimeoutException("timed out"), _response(200, "ok")],
    )
    text = ja_lyrics.post_chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert text == "ok"
    assert [item["model"] for item in calls] == ["gpt-5.6-luna", "gpt-5.6-luna"]
    assert ja_lyrics.agent_model_used() == "gpt-5.6-luna"


def test_grok_fallback_after_luna_keeps_failing(monkeypatch):
    calls = _install(
        monkeypatch,
        [
            httpx.TimeoutException("timed out"),
            httpx.TimeoutException("timed out"),
            _response(200, "from-grok"),
        ],
    )
    text = ja_lyrics.post_chat([{"role": "user", "content": "hi"}], temperature=0.1)
    assert text == "from-grok"
    assert [item["model"] for item in calls] == [
        "gpt-5.6-luna",
        "gpt-5.6-luna",
        "grok-4.6",
    ]
    assert ja_lyrics.agent_model_used() == "grok-4.6"


def test_auth_failure_does_not_fall_back(monkeypatch):
    calls = _install(monkeypatch, [_response(401, "")])
    with pytest.raises(RuntimeError, match="鉴权失败"):
        ja_lyrics.post_chat([{"role": "user", "content": "hi"}], temperature=0.1)
    assert [item["model"] for item in calls] == ["gpt-5.6-luna"]


def test_both_models_exhausted_raises(monkeypatch):
    calls = _install(
        monkeypatch,
        [httpx.TimeoutException("timed out")] * 4,
    )
    with pytest.raises(AgentUnavailable, match="grok-4.6"):
        ja_lyrics.post_chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert [item["model"] for item in calls] == ["gpt-5.6-luna", "gpt-5.6-luna", "grok-4.6", "grok-4.6"]


def test_alignment_request_falls_back_and_checks_json(monkeypatch):
    payload = json.dumps({"schema": "lovktv-sung-lyrics-v1", "language": "ja", "rows": []})
    calls = _install(
        monkeypatch,
        [
            _response(200, "[1]"),
            _response(200, "[2]"),
            _response(200, payload),
        ],
    )
    text = alignment._request_content([{"role": "user", "content": "align"}])
    assert json.loads(text)["rows"] == []
    assert [item["model"] for item in calls] == ["gpt-5.6-luna", "gpt-5.6-luna", "grok-4.6"]
    assert calls[0]["temperature"] == 0.0


def test_same_fallback_name_is_not_tried_twice(monkeypatch):
    monkeypatch.setattr(ja_lyrics, "agent_model", lambda: "grok-4.6")
    assert ja_lyrics.agent_model_chain() == ["grok-4.6"]
