# 🎙️ Speech AI Data Pipeline (Production Standard)
> **Hệ thống Thu thập, Tách Nguồn Âm Thanh AI Độc Lập (Demucs & MelBand RoFormer), Cắt Lát Giọng Nói Silero VAD & Chống Trùng Lặp Chuẩn Hóa Dataset ASR/TTS.**

---

## 📌 1. Giới Thiệu Dự Án

Kho mã nguồn chuẩn hóa quy trình kỹ thuật dữ liệu âm thanh (Speech Data Engineering) từ nguồn mạng xã hội (TikTok, Facebook Reels, Shorts) đến tập dữ liệu Gold Dataset sẵn sàng nạp vào các mô hình huấn luyện Speech AI (OpenAI Whisper, Conformer, VITS).

### 🎯 Chuẩn Dữ Liệu Đầu Ra (Gold Standard)
- **Định dạng:** WAV 16,000 Hz (16 kHz), Single Channel (Mono), 16-bit PCM.
- **Loudness:** Chuẩn hóa âm lượng target `-20 LUFS`.
- **Độ dài phân đoạn:** $3.0\text{s} - 15.0\text{s}$ (cắt tự nhiên theo biên giới câu nói).
- **Metadata đi kèm (`metadata.jsonl`):**
  ```json
  {
    "audio_path": "gold_dataset/tt_7412345678901234567_01.wav",
    "item_id": "tt_7412345678901234567_01",
    "duration_seconds": 8.45,
    "spectral_flatness": 0.04125,
    "snr_estimate_db": 24.5,
    "source_url": "https://www.tiktok.com/@user/video/7412345678901234567",
    "separation_model": "demucs",
    "label": "research_only",
    "processed_at": "2026-09-17T20:30:00"
  }
  ```

---

## 🏗️ 2. Cấu Trúc Mã Nguồn

```text
speech_pipeline/
├── configs/
│   └── pipeline_config.yaml    # Cấu hình ngưỡng VAD, tham số Model, Quality Gate
├── src/
│   ├── crawler/                # Module trích xuất audio từ URLs
│   ├── separation/             # Dual Engine: demucs_engine.py & melband_engine.py
│   ├── vad_slicer/             # Module cắt lát giọng nói Silero VAD
│   ├── dedup/                  # Module chống trùng lặp Waveform Quantized Fingerprint
│   ├── quality_gate/           # Module đo lường SNR & Spectral Flatness
│   └── pipeline.py             # CLI Master Pipeline kết nối toàn trình
├── scripts/
│   ├── run_demucs_pipeline.sh  # Script chạy nhánh Demucs
│   └── run_melband_pipeline.sh # Script chạy nhánh MelBand-RoFormer
├── tests/
│   └── test_pipeline.py        # Unit test kiểm tra format wav, dedup, quality gate
├── requirements.txt            # Danh sách thư viện phụ thuộc
├── .gitignore
├── README.md                   # Hướng dẫn vận hành
└── SUMMARY.md                  # Báo cáo chuyên sâu giải trình Mentor
```

---

## ⚙️ 3. Yêu Cầu Môi Trường & Cài Đặt

- **Hệ điều hành:** Linux Ubuntu 22.04/24.04, WSL2, hoặc Windows 11.
- **Python:** $\ge 3.10$.
- **GPU:** NVIDIA GPU $\ge 8\text{GB}$ VRAM (khuyến nghị RTX 3060/4090/A4000/5060Ti, CUDA $\ge 12.1$).
- **FFmpeg:** Đã cài đặt trên hệ thống (`sudo apt update && sudo apt install -y ffmpeg`).

### Cài Đặt Thư Viện:
```bash
git clone https://github.com/conheo-map/ToolCrawl.git
cd ToolCrawl/speech_pipeline
pip install -r requirements.txt
```

---

## 🚀 4. Hướng Dẫn Chạy Nhanh (Quickstart - 1 Dòng Lệnh)

### 🔹 Cách 1: Chạy với mô hình Meta AI Demucs v4 (Nhanh, thông lượng lớn)
```bash
python src/pipeline.py --urls urls.txt --model demucs --output data/demucs_gold --device cuda
```

### 🔹 Cách 2: Chạy với mô hình Mel-Band RoFormer (Chất lượng Studio SOTA)
```bash
python src/pipeline.py --urls urls.txt --model melband --output data/melband_gold --device cuda
```

### 📋 Giải thích tham số CLI:
- `--urls`: Đường dẫn file `.txt` chứa danh sách link TikTok / Reels (mỗi dòng 1 URL).
- `--model`: Lựa chọn mô hình tách nhạc (`demucs` hoặc `melband`).
- `--output`: Thư mục lưu kết quả cuối cùng (tự động tạo `gold_dataset/` và `metadata.jsonl`).
- `--device`: Thiết bị chạy (`cuda` hoặc `cpu`).
- `--limit`: (Tùy chọn) Giới hạn số lượng URL cần cào để test nhanh.

---

## 🧪 5. Kiểm Thử Mã Nguồn (Unit Testing)

Chạy bộ unit test để đảm bảo hệ thống đạt 100% tiêu chuẩn kỹ thuật trước khi chạy dữ liệu thật:
```bash
pytest -v tests/test_pipeline.py
```
*Kết quả: 100% tests PASS (Kiểm tra định dạng chuẩn 16k/1ch PCM16, thuật toán Dedup, và Quality Gate).*

---

## 💡 6. Cẩm Nang Xử Lý Sự Cố & Vận Hành Trên RunPod / Cloud

### 1. Tránh Lỗi CUDA Out Of Memory (OOM)
- Khi gặp video dài $> 5$ phút, Demucs và RoFormer có thể gây tràn VRAM nếu inference 1 lần.
- **Giải pháp:** Pipeline đã tích hợp chunking và lệnh giải phóng VRAM `torch.cuda.empty_cache()` ngay sau mỗi lần xử lý từng track vocal.

### 2. Mount Google Drive Không Bị Mất Token Trên Headless RunPod
- Để đồng bộ kết quả lên Google Drive từ RunPod mà không cần mở trình duyệt web:
  1. Tạo file `rclone.conf` từ máy local.
  2. Copy trực tiếp nội dung `rclone.conf` vào `/root/.config/rclone/rclone.conf` trên RunPod.
  3. Đồng bộ đa luồng lên Drive:
     ```bash
     rclone copy data/demucs_gold/gold_dataset "gdrive:Dataset/Week5/audio" --transfers 32 --checkers 64 -P
     ```
