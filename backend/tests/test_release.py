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
    assert "UVR_MDXNET_KARA_2.onnx" in text
    assert "/opt/lovktv/models" in text
    assert text.index("UVR_MDXNET_KARA_2.onnx") < text.index("COPY frontend")
    assert "onnxruntime" in (ROOT / "backend" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "openai-whisper" not in text
    assert "pytorch.org" not in text


def test_compose_exposes_port_and_data_volume():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "8787:8787" in text
    assert "./data:/app/data" in text
    assert "LOVKTV_DATA" in text
    assert "LOVKTV_MODELS" in text
    assert "ALIYUN_OSS_ACCESS_KEY_ID" in text
    assert "LOVKTV_OSS_PREFIX" in text
    assert "LOVKTV_DATABASE_URL" in text
    assert "LOVKTV_APP_UPLOAD_TOKEN" in text
    assert "LOVKTV_ADS_OPEN" in text
    assert "LOVKTV_ASR_MODEL" in text
    assert "LOVKTV_WHISPER_MODEL" in text
    assert "LOVKTV_WHISPER_COMPUTE_TYPE" in text
    assert "healthcheck" in text
    assert "/api/host" in text
    assert "restart:" in text


def test_prod_compose_binds_localhost_and_reuses_origin_cert():
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "deploy" / "nginx" / "ktv.lovbrowser.com.conf").read_text(
        encoding="utf-8"
    )
    assert "127.0.0.1:8790:8787" in compose
    assert "ktv.lovbrowser.com" in compose
    assert "ktv.lovbrowser.com" in nginx
    assert "/etc/ssl/lovbrowser/lovbrowser.com.pem" in nginx
    assert "127.0.0.1:8790" in nginx


def test_version_file_drives_apk_and_git_tag():
    version = (ROOT / "VERSION").read_text(encoding="utf-8")
    assert "name=" in version
    assert "code=" in version
    tv = (ROOT / "android-tv" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    phone = (ROOT / "android-phone" / "app" / "build.gradle.kts").read_text(
        encoding="utf-8"
    )
    publish = (ROOT / "scripts" / "publish-apps.py").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "fun lovktvVersion()" in tv
    assert "fun lovktvVersion()" in phone
    assert "versionName = appVersionName" in tv
    assert "versionName = appVersionName" in phone
    assert "from version import read_version" in publish
    assert "python scripts/version.py tag" in agents
    assert 'id="tvVersion"' in (ROOT / "frontend" / "public" / "tv.html").read_text(
        encoding="utf-8"
    )
    assert 'id="whoVersion"' in (ROOT / "frontend" / "public" / "m.html").read_text(
        encoding="utf-8"
    )


def test_dockerignore_keeps_vendor_and_media_out():
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "vendor" in text
    assert "data" in text
    assert "android-tv" in text
    assert ".venv" in text
