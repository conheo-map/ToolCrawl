# Dockerfile for Facebook & TikTok Audio Crawler
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

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p errors .checkpoints logs Week2

# Default entrypoint
ENTRYPOINT ["python", "main.py"]
CMD ["--platform", "tiktok", "--keyword", "review quán ăn", "--workers", "4"]
