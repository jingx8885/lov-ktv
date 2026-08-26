from pathlib import Path

from lovktv.pipeline.mdx_onnx import MODEL_NAME, ensure_separator_model, model_path, model_status


def test_model_path_prefers_lovktv_models(tmp_path, monkeypatch):
    baked = tmp_path / "opt" / MODEL_NAME
    baked.parent.mkdir(parents=True)
    baked.write_bytes(b"onnx")
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("LOVKTV_MODELS", str(baked.parent))
    monkeypatch.setenv("LOVKTV_DATA", str(data))
    monkeypatch.setattr("lovktv.pipeline.mdx_onnx.IMAGE_MODELS_DIR", tmp_path / "opt-missing")
    monkeypatch.setattr("lovktv.pipeline.mdx_onnx.DATA_DIR", data)
    assert model_path() == baked.resolve()


def test_ensure_separator_model_downloads_when_missing(tmp_path, monkeypatch):
    dest_dir = tmp_path / "models"
    monkeypatch.setenv("LOVKTV_MODELS", str(dest_dir))
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path / "data"))
    monkeypatch.setattr("lovktv.pipeline.mdx_onnx.IMAGE_MODELS_DIR", tmp_path / "opt-missing")
    monkeypatch.setattr("lovktv.pipeline.mdx_onnx.DATA_DIR", tmp_path / "data")

    def fake_download(url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FAKE-ONNX")

    monkeypatch.setattr("lovktv.pipeline.mdx_onnx.download_file", fake_download)
    path = ensure_separator_model()
    assert path.exists()
    assert path.read_bytes() == b"FAKE-ONNX"
    assert path.name == MODEL_NAME


def test_model_status_reports_separator_and_whisper(tmp_path, monkeypatch):
    dest = tmp_path / "models" / MODEL_NAME
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"onnx")
    monkeypatch.setenv("LOVKTV_MODELS", str(dest.parent))
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path / "data"))
    monkeypatch.setattr("lovktv.pipeline.mdx_onnx.IMAGE_MODELS_DIR", tmp_path / "opt-missing")
    monkeypatch.setattr("lovktv.pipeline.mdx_onnx.whisper_ready", lambda: True)
    status = model_status()
    assert status["separator"] is True
    assert status["whisper"] is True
    assert MODEL_NAME in status["separator_path"]
