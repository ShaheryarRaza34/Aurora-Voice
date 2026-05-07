FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    pkg-config \
    gcc \
    g++ \
    make \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libavutil-dev \
    libavdevice-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Piper TTS
RUN wget -O piper.tar.gz https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz \
    && tar -xzf piper.tar.gz \
    && mv piper /opt/piper \
    && ln -s /opt/piper/piper /usr/local/bin/piper \
    && rm piper.tar.gz

ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/piper

# Install Python dependencies  
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Download spaCy model (fix download command)
RUN python -m spacy download en_core_web_sm --direct || \
    pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

# Piper voice models (bundled in image; default PIPER_MODEL path is under /app/models)
COPY models /app/models

# Copy application code
COPY backend/*.py ./

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "server.py"]
