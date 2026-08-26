from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_is_release_ready():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ffmpeg" in text
    assert "yt-dlp" in text
    assert "HEALTHCHECK" in text
    assert "8787" in text
    assert "COPY vendor" not in text
    assert "uvicorn" in text
    assert "lovktv.main:app" in text


def test_compose_exposes_port_and_data_volume():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "8787:8787" in text
    assert "./data:/app/data" in text
    assert "LOVKTV_DATA" in text
    assert "healthcheck" in text
    assert "/api/host" in text
    assert "restart:" in text


def test_dockerignore_keeps_vendor_and_media_out():
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "vendor" in text
    assert "data" in text
    assert "android-tv" in text
    assert ".venv" in text
