import json
import sys
import types
import wave

from lovktv.pipeline.transcribe import _parse_whisper_json, transcribe_words


def test_parse_whisper_prefers_word_timestamps(tmp_path):
    path = tmp_path / "asr.json"
    path.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 9.9,
                        "end": 13.8,
                        "text": "どうでもいいような夜だけど",
                        "words": [
                            {"word": "どうでも", "start": 9.9, "end": 10.4},
                            {"word": "いいような", "start": 10.4, "end": 11.2},
                            {"word": "夜だけど", "start": 11.2, "end": 13.8},
                        ],
                    },
                    {"start": 25.0, "end": 29.0, "text": "まだ止まった刻む針も"},
                ]
            }
        ),
        encoding="utf-8",
    )
    words = _parse_whisper_json(path)
    assert words[0]["text"] == "どうでも"
    assert words[0]["start_ms"] == 9900
    assert words[0]["end_ms"] == 10400
    assert words[0]["segment"] == 0
    assert words[-1]["text"] == "まだ止まった刻む針も"
    assert words[-1]["start_ms"] == 25000
    assert words[-1]["segment"] == 1


def test_transcribe_waits_for_existing_whisper(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"x")
    started = {"run": 0}

    def fake_pids(_path):
        return [4242]

    def fake_wait(audio_path, sibling, cache_path, timeout=900):
        sibling.parent.mkdir(parents=True, exist_ok=True)
        sibling.write_text(
            json.dumps(
                {
                    "segments": [
                        {
                            "start": 1.0,
                            "end": 2.0,
                            "text": "hello",
                            "words": [{"word": "hello", "start": 1.0, "end": 2.0}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return _parse_whisper_json(sibling)

    def fake_run(*_args, **_kwargs):
        started["run"] += 1
        raise AssertionError("should not start another whisper")

    monkeypatch.setattr(transcribe, "whisper_pids_for", fake_pids)
    monkeypatch.setattr(transcribe, "_wait_for_whisper_result", fake_wait)
    monkeypatch.setattr(transcribe.subprocess, "run", fake_run)
    words = transcribe_words(audio, "en", cache_path=tmp_path / "asr.json")
    assert words[0]["text"] == "hello"
    assert started["run"] == 0


def test_transcribe_waits_for_other_whisper(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"x")
    started = {"run": 0, "idle": 0}

    def fake_pids_for(_path):
        return []

    def fake_any():
        return [4242] if started["idle"] == 0 else []

    def fake_idle(timeout=900):
        started["idle"] += 1

    def fake_run(*_args, **_kwargs):
        started["run"] += 1

        class Result:
            returncode = 1

        return Result()

    monkeypatch.setattr(transcribe, "whisper_pids_for", fake_pids_for)
    monkeypatch.setattr(transcribe, "any_whisper_pids", fake_any)
    monkeypatch.setattr(transcribe, "_wait_until_whisper_idle", fake_idle)
    # Keep the test independent of whether the optional whisper CLI is
    # installed on the host; the subprocess call itself is mocked below.
    monkeypatch.setattr(transcribe, "WHISPER_BIN", "whisper")
    monkeypatch.setattr(transcribe.subprocess, "run", fake_run)
    transcribe_words(audio, "ja", cache_path=tmp_path / "asr.json")
    assert started["idle"] == 1
    assert started["run"] == 1


def test_transcribe_uses_faster_whisper_when_cli_missing(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    class Word:
        word, start, end = " hello ", 1.25, 2.5

    class Segment:
        start, end, text, words = 1.25, 2.5, "hello", [Word()]

    class Model:
        def transcribe(self, *_args, **_kwargs):
            return iter([Segment()]), types.SimpleNamespace(duration=4.0)

    fake_module = types.SimpleNamespace(WhisperModel=lambda *args, **kwargs: Model())
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.setattr(transcribe, "WHISPER_BIN", None)
    transcribe._faster_whisper_model.cache_clear()
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"x")
    words = transcribe_words(audio, "en", cache_path=tmp_path / "asr.json")
    assert words == [
        {"text": "hello", "start_ms": 1250, "end_ms": 2500, "segment": 0}
    ]


def test_transcribe_uses_fish_remote_with_interpolated_timestamps(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"fake audio")
    monkeypatch.setenv("LOVKTV_ASR_MODEL", "fish-transcribe-1")
    monkeypatch.setenv("LOVKTV_AGENT_URL", "https://agent.example")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "secret")
    monkeypatch.setattr(transcribe, "whisper_pids_for", lambda _path: [])
    monkeypatch.setattr(transcribe, "any_whisper_pids", lambda: [])

    seen = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "duration": 1.0,
                "language_code": "en",
                "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
                "text": "hello world",
            }

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(transcribe.httpx, "post", fake_post)
    words = transcribe.transcribe_words(audio, "en", cache_path=tmp_path / "asr.json")

    assert seen["url"] == "https://agent.example/v1/audio/transcriptions"
    assert seen["headers"] == {"Authorization": "Bearer secret"}
    assert seen["data"] == {
        "model": "fish-transcribe-1",
        "language": "en",
        "ignore_timestamps": "false",
    }
    assert [word["text"] for word in words] == ["hello", "world"]
    assert words[0]["start_ms"] == 0
    assert words[-1]["end_ms"] == 1000
    assert '"provider": "fish-audio"' in (tmp_path / "asr.json").read_text()


def test_transcribe_uses_grok_verbose_word_timestamps(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"fake audio")
    monkeypatch.setenv("LOVKTV_ASR_MODEL", "grok-stt")
    monkeypatch.setenv("LOVKTV_AGENT_URL", "https://agent.example/v1")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "secret")
    monkeypatch.setattr(transcribe, "whisper_pids_for", lambda _path: [])
    monkeypatch.setattr(transcribe, "any_whisper_pids", lambda: [])

    seen = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "task": "transcribe",
                "text": "Hello world",
                "words": [
                    {"start": 0.04, "end": 0.42, "text": "Hello,"},
                    {"start": 0.9, "end": 1.25, "text": "world"},
                ],
            }

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(transcribe.httpx, "post", fake_post)
    words = transcribe.transcribe_words(audio, "en", cache_path=tmp_path / "asr.json")

    assert seen["url"] == "https://agent.example/v1/audio/transcriptions"
    assert seen["data"] == {
        "model": "grok-stt",
        "language": "en",
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word",
    }
    assert words == [
        {"text": "Hello,", "start_ms": 40, "end_ms": 420, "segment": 0},
        {"text": "world", "start_ms": 900, "end_ms": 1250, "segment": 1},
    ]
    assert '"provider": "grok-stt"' in (tmp_path / "asr.json").read_text()


def test_grok_keeps_successful_chunks_when_a_later_chunk_fails(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"fake audio")
    chunk_one = tmp_path / "chunk-one.mp3"
    chunk_two = tmp_path / "chunk-two.mp3"
    chunk_one.write_bytes(b"one")
    chunk_two.write_bytes(b"two")
    monkeypatch.setenv("LOVKTV_ASR_MODEL", "grok-stt")
    monkeypatch.setenv("LOVKTV_AGENT_URL", "https://agent.example")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "secret")
    monkeypatch.setattr(transcribe, "whisper_pids_for", lambda _path: [])
    monkeypatch.setattr(transcribe, "any_whisper_pids", lambda: [])
    monkeypatch.setattr(
        transcribe,
        "_remote_chunks",
        lambda _path, audio_format="wav": iter([(chunk_one, 0.0), (chunk_two, 30.0)]),
    )
    monkeypatch.setattr(transcribe, "_audio_has_voice", lambda _path: True)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"words": [{"start": 0.1, "end": 0.4, "text": "kept"}]}

    calls = 0

    def fake_post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("upstream chunk failed")
        return Response()

    monkeypatch.setattr(transcribe.httpx, "post", fake_post)
    words = transcribe.transcribe_words(audio, "en", cache_path=tmp_path / "asr.json")

    assert calls == 2
    assert words == [{"text": "kept", "start_ms": 100, "end_ms": 400, "segment": 0}]
    assert '"provider": "grok-stt"' in (tmp_path / "asr.json").read_text()


def test_remote_model_does_not_reuse_legacy_whisper_cache(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"fake audio")
    cache = tmp_path / "asr.json"
    cache.write_text(
        json.dumps({"language": "ja", "segments": [{"start": 0, "end": 1, "text": "旧缓存"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOVKTV_ASR_MODEL", "grok-stt")
    monkeypatch.setenv("LOVKTV_AGENT_URL", "https://agent.example")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "secret")
    monkeypatch.setattr(transcribe, "whisper_pids_for", lambda _path: [])
    monkeypatch.setattr(transcribe, "any_whisper_pids", lambda: [])

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "new", "words": [{"start": 0, "end": 1, "text": "new"}]}

    monkeypatch.setattr(transcribe.httpx, "post", lambda *_args, **_kwargs: Response())
    words = transcribe.transcribe_words(audio, "en", cache_path=cache)
    assert words[0]["text"] == "new"


def test_remote_skips_silent_wav(monkeypatch, tmp_path):
    from lovktv.pipeline import transcribe

    audio = tmp_path / "silent.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)
    monkeypatch.setenv("LOVKTV_ASR_MODEL", "grok-stt")
    monkeypatch.setenv("LOVKTV_AGENT_URL", "https://agent.example")
    monkeypatch.setenv("LOVKTV_AGENT_KEY", "secret")
    monkeypatch.setattr(transcribe, "httpx", types.SimpleNamespace(post=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("silent chunk must be skipped"))))
    assert transcribe.transcribe_words(audio, "en", cache_path=tmp_path / "asr.json") == []
