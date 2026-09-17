#!/bin/bash
# ==============================================================================
# SETUP CHUẨN 100% CHO MÁY CLOUD GPU MỚI (EzyCloudX / Ubuntu 22.04 / 24.04)
# Tự động cài đặt đầy đủ môi trường, CUDA PyTorch, FFmpeg, Demucs & Soundfile
# ==============================================================================

set -e

echo "=================================================================="
echo "🚀 BẮT ĐẦU THIẾT LẬP MÔI TRƯỜNG CLOUD GPU (CHUẨN 100% KHÔNG LỖI)"
echo "=================================================================="

# 1. Cài đặt các gói hệ thống cần thiết (FFmpeg, Git, Python, Rclone, Screen)
echo "[1/4] Đang cài đặt FFmpeg, Git, Rclone, Screen, Unzip..."
sudo apt update -y
sudo apt install -y ffmpeg git python3-pip python3-venv zip unzip curl rclone screen

# 2. Cài đặt PyTorch với CUDA mới nhất
echo "[2/4] Đang cài đặt PyTorch CUDA 12.1..."
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Cài đặt Demucs, Soundfile, yt-dlp và các thư viện xử lý
echo "[3/4] Đang cài đặt Demucs AI, Soundfile, yt-dlp..."
pip install demucs soundfile yt-dlp requests tqdm

# 4. Kiểm tra GPU và nạp trước model Demucs vào cache
echo "[4/4] Kiểm tra GPU NVIDIA & Nạp Model Demucs..."
python3 -c "
import torch
print(f'  - GPU Co san: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'  - GPU Model: {torch.cuda.get_device_name(0)}')
    print(f'  - VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB')

from demucs.pretrained import get_model
_ = get_model('htdemucs')
print('  - Demucs Model: Da san sang trong cache 100%!')
"

echo "=================================================================="
echo "🎉 THIẾT LẬP HOÀN TẤT 100%! MÁY ĐÃ SẴN SÀNG CHẠY PIPELINE!"
echo "=================================================================="
