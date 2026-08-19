# Dockerfile for Facebook & TikTok Audio Crawler
# with Hybrid Pipeline: Demucs AI Vocal Separator
FROM python:3.12-slim

# Install system dependencies including FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install lightweight CPU-only PyTorch first (~150MB thay vì 4GB CUDA)
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Copy requirements first to leverage Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-tải mô hình Demucs htdemucs vào cache image
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')" || true

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p errors .checkpoints logs Week2

# Default entrypoint
ENTRYPOINT ["python", "main.py"]
CMD ["--platform", "tiktok", "--keyword", "review quán ăn", "--workers", "4"]
