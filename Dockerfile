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

# Copy requirements first to leverage Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-tải mô hình Demucs htdemucs vào cache image
# (htdemucs_ft ~100MB sẽ tải khi chạy lần đầu)
# Dùng htdemucs (~80MB) để tải sẵn vào image cho tốc độ khởi động nhanh
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')" || true

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p errors .checkpoints logs Week2

# Default entrypoint
ENTRYPOINT ["python", "main.py"]
CMD ["--platform", "tiktok", "--keyword", "review quán ăn", "--workers", "4"]
