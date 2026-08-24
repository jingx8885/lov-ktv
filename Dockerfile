FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend /app/backend
COPY frontend /app/frontend
ENV PYTHONPATH=/app/backend
ENV LOVKTV_DATA=/app/data
RUN pip install --no-cache-dir -e /app/backend
EXPOSE 8787
CMD ["python", "-m", "uvicorn", "lovktv.main:app", "--host", "0.0.0.0", "--port", "8787"]
