FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend /app/backend
COPY frontend /app/frontend

ENV PYTHONPATH=/app/backend \
    LOVKTV_DATA=/app/data \
    LOVKTV_MODELS=/opt/lovktv/models \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Separator is UVR ONNX + onnxruntime. Keep it under /opt so ./data cannot hide it.
# Official LRC interpolation works without a local ASR stack.
RUN pip install --no-cache-dir -e /app/backend yt-dlp \
    && mkdir -p /app/data /opt/lovktv/models \
    && curl -fsSL --retry 3 -o /opt/lovktv/models/UVR_MDXNET_KARA_2.onnx \
        https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR_MDXNET_KARA_2.onnx \
    && test -s /opt/lovktv/models/UVR_MDXNET_KARA_2.onnx

EXPOSE 8787
HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=6 \
    CMD curl -fsS http://127.0.0.1:8787/api/host >/dev/null

CMD ["python", "-m", "uvicorn", "lovktv.main:app", "--host", "0.0.0.0", "--port", "8787"]
