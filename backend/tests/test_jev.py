import pytest

from lovktv.agents import jev
from lovktv.agents.jev import JevError, Question, try_evaluate
from lovktv.workers import lyric_audit


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text or (str(payload) if payload else "")

    def json(self):
        return self._payload


class FakeHttp:
    """Minimal httpx stand-in: records the last request, replays responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, content=None, json=None):
        self.calls.append({"url": url, "headers": headers, "content": content})
        if not self.responses:
            raise AssertionError("unexpected extra call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _monkey_cfg(monkeypatch, base="http://gw/v1", key="k"):
    monkeypatch.setattr(jev, "jev_base_url", lambda: base)
    monkeypatch.setattr(jev, "jev_api_key", lambda: key)


def test_evaluate_returns_typed_answers(monkeypatch):
    _monkey_cfg(monkeypatch)
    payload = {
        "model": "jev-1.13.0",
        "answers": {
            "ok": {"type": "noul", "noul": 0.87},
            "kind": {"type": "choice", "choice": "romaji", "confidence": 0.9},
        },
        "usage": {"input_tokens": 100},
    }
    http = FakeHttp([FakeResp(200, payload)])
    result = jev.evaluate(
        {"line": "itsumo no you ni"},
        {
            "ok": Question(type="noul", instructions="plausible?"),
            "kind": Question(
                type="choice",
                instructions="script?",
                criteria={"romaji": "latin", "japanese": "kana"},
            ),
        },
        client=http,
    )
    assert result.model == "jev-1.13.0"
    assert result.answers["ok"]["noul"] == 0.87
    assert result.answers["kind"]["choice"] == "romaji"
    assert http.calls[0]["url"] == "http://gw/v1/systemone"
    assert b"systemone" not in http.calls[0]["content"]  # url only, not body
    assert b"itsumo" in http.calls[0]["content"]


def test_evaluate_retries_then_raises(monkeypatch):
    _monkey_cfg(monkeypatch)
    monkeypatch.setattr(jev.time, "sleep", lambda _s: None)
    http = FakeHttp(
        [jev.httpx.ConnectError("boom"), FakeResp(529, text="busy"), FakeResp(500, text="x")]
    )
    with pytest.raises(JevError):
        jev.evaluate({}, {"q": Question(type="noul", instructions="?")}, client=http)
    assert len(http.calls) == 3


def test_evaluate_missing_answer_is_error(monkeypatch):
    _monkey_cfg(monkeypatch)
    http = FakeHttp([FakeResp(200, {"answers": {}})])
    with pytest.raises(JevError, match="missing answers"):
        jev.evaluate({}, {"q": Question(type="noul", instructions="?")}, client=http)


def test_try_evaluate_fail_open(monkeypatch):
    _monkey_cfg(monkeypatch, base="", key="")
    result = try_evaluate({}, {"q": Question(type="noul", instructions="?")})
    assert result.error
    assert result.answers == {}


def test_marshal_rejects_bad_question():
    with pytest.raises(JevError):
        jev._marshal_questions({"q": Question(type="choice", instructions="?")})
    with pytest.raises(JevError):
        jev._marshal_questions({"q": Question(type="score", instructions="?", levels=["a"])})
    out = jev._marshal_questions(
        {"s": Question(type="score", instructions="?", levels=["low", "mid", "high"])}
    )
    assert out["s"]["criteria"] == ["low", "mid", "high"]


# --- audit shadow report ----------------------------------------------------


def _cue(text, zh="", tokens=None):
    cue = {"text": text, "start_ms": 0, "end_ms": 1000}
    if zh:
        cue["zh"] = zh
        cue["translation"] = zh
    cue["tokens"] = tokens or [{"text": text, "reading": ""}]
    return cue


class ScriptedJev:
    """Answers noul questions from a per-question-id probability map."""

    def __init__(self, probs):
        self.probs = probs
        self.calls = []

    def post(self, url, headers=None, content=None, json=None):
        import json as _json

        self.calls.append(_json.loads(content))
        answers = {}
        for qid in _json.loads(content)["questions"]:
            answers[qid] = {"type": "noul", "noul": self.probs.get(qid, 0.9)}
        return FakeResp(200, {"model": "jev-test", "answers": answers, "usage": {}})


def test_jev_report_flags_bad_zh_and_reading(monkeypatch):
    _monkey_cfg(monkeypatch)
    monkeypatch.setattr(
        lyric_audit, "get_song", lambda _sid: {"title": "t", "artist": "a"}
    )
    timeline = {
        "language": "ja",
        "cues": [
            _cue(
                "君の心が動いたよ",
                zh="我们一起去吃晚饭",
                tokens=[
                    {"text": "君", "reading": "くん"},
                    {"text": "心", "reading": "こころ"},
                ],
            ),
            _cue(
                "いつものように",
                zh="一如既往",
                tokens=[{"text": "いつものように", "reading": ""}],
            ),
        ],
    }
    fake = ScriptedJev({"zh_ok_1": 0.05, "read_ok_1": 0.1, "zh_ok_2": 0.95, "read_ok_2": 0.9})
    report = lyric_audit._jev_report("s1", timeline, client=fake)
    assert report["checked"] == 2
    assert report["bad_zh"] == [
        {"line": "君の心が動いたよ", "zh": "我们一起去吃晚饭", "p": 0.05}
    ]
    assert report["bad_reading"] == [{"line": "君の心が動いたよ", "p": 0.1}]
    assert report["unsure"] == []
    # one batched call, per-cue questions
    assert len(fake.calls) == 1
    assert set(fake.calls[0]["questions"]) == {
        "zh_ok_1", "read_ok_1", "zh_ok_2", "read_ok_2"
    }


def test_jev_report_skips_credit_and_solfege(monkeypatch):
    _monkey_cfg(monkeypatch)
    monkeypatch.setattr(lyric_audit, "get_song", lambda _sid: {})
    timeline = {
        "language": "en",
        "cues": [
            _cue("la la la", zh=""),
            _cue("Written by Someone", zh=""),
            _cue("I still love you", zh="我还爱你"),
        ],
    }
    fake = ScriptedJev({"zh_ok_1": 0.9})
    report = lyric_audit._jev_report("s1", timeline, client=fake)
    # solfege is skipped; the credit-looking line is not caught by the
    # credit heuristic and goes to Jev with the real sung line.
    assert report["checked"] == 2
    assert report["flagged"] == 0


def test_jev_report_fail_open(monkeypatch):
    _monkey_cfg(monkeypatch, base="", key="")
    monkeypatch.setattr(lyric_audit, "get_song", lambda _sid: {})
    timeline = {"language": "en", "cues": [_cue("hold me", zh="抱住我")]}
    report = lyric_audit._jev_report("s1", timeline)
    assert report["error"]
    assert report["flagged"] == 0

