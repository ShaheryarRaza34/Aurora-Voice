# backend/Dockerfile
FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# deps for webrtcvad wheels / building, and audio libs for piper
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install python deps + piper binary
COPY requirements.txt .
RUN pip install -r requirements.txt && pip install piper-tts

# app code
COPY server.py .

EXPOSE 8000

# env defaults (override in compose if needed)
ENV ASR_MODEL=medium \
    ASR_DEVICE=auto \
    ASR_COMPUTE=int8_float16 \
    PIPER_MODEL=/app/models/en_US-amy-low.onnx \
    PIPER_OUT=/app/out.wav

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
