FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONPATH=/app/backend \
    LOVKTV_DATA=/app/data \
    LOVKTV_MODELS=/opt/lovktv/models \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN mkdir -p /app/backend/lovktv /app/data /opt/lovktv/models \
    && printf '%s\n' '__version__ = "0"' > /app/backend/lovktv/__init__.py \
    && pip install --no-cache-dir -e /app/backend yt-dlp \
    && curl -fsSL --retry 3 -o /opt/lovktv/models/UVR_MDXNET_KARA_2.onnx \
        https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR_MDXNET_KARA_2.onnx \
    && test -s /opt/lovktv/models/UVR_MDXNET_KARA_2.onnx

FROM base AS app

COPY backend /app/backend
COPY frontend /app/frontend
COPY scripts/build-frontend-dist.py /app/scripts/build-frontend-dist.py
RUN python /app/scripts/build-frontend-dist.py \
    --source /app/frontend/public \
    --output /app/frontend/frontend-dist
RUN pip install --no-deps --no-cache-dir -e /app/backend

EXPOSE 8787
HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=6 \
    CMD curl -fsS http://127.0.0.1:8787/healthz >/dev/null

CMD ["python", "-m", "uvicorn", "lovktv.main:app", "--host", "0.0.0.0", "--port", "8787"]
