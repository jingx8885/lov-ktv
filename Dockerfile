FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend /app/backend
COPY frontend /app/frontend

ENV PYTHONPATH=/app/backend \
    LOVKTV_DATA=/app/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir -e /app/backend yt-dlp \
    && mkdir -p /app/data

EXPOSE 8787
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=6 \
    CMD curl -fsS http://127.0.0.1:8787/api/host >/dev/null

CMD ["python", "-m", "uvicorn", "lovktv.main:app", "--host", "0.0.0.0", "--port", "8787"]
