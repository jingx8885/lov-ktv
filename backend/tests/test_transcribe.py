import json

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
            json.dumps({"segments": [{"start": 1.0, "end": 2.0, "text": "hello", "words": [{"word": "hello", "start": 1.0, "end": 2.0}]}]}),
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
    monkeypatch.setattr(transcribe.subprocess, "run", fake_run)
    transcribe_words(audio, "ja", cache_path=tmp_path / "asr.json")
    assert started["idle"] == 1
    assert started["run"] == 1
