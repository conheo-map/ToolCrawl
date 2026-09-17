# 🎙️ Hệ thống xử lý dữ liệu âm thanh giọng nói

> **Hệ thống thu thập, tách nguồn âm thanh độc lập bằng Demucs và Mel-Band RoFormer, cắt lát giọng nói Silero VAD và lọc trùng lặp chuẩn hóa dữ liệu huấn luyện.**

---

## 📌 1. Giới thiệu dự án

Kho mã nguồn chuẩn hóa quy trình xử lý dữ liệu âm thanh từ các nền tảng mạng xã hội như TikTok, Facebook Reels, Shorts thành tập dữ liệu sạch, sẵn sàng nạp vào các mô hình huấn luyện tiếng nói như Whisper, Conformer hoặc VITS.

### 🎯 Chuẩn dữ liệu đầu ra
- **Định dạng:** WAV 16.000 Hz, kênh đơn, 16-bit PCM.
- **Độ lớn âm thanh:** Chuẩn hóa âm lượng mức -20 LUFS.
- **Độ dài phân đoạn:** Từ 3,0 đến 15,0 giây, được cắt tự nhiên theo biên giới câu nói.
- **Thông tin đi kèm (`metadata.jsonl`):**
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

## 🏗️ 2. Cấu trúc mã nguồn

```text
speech_pipeline/
├── configs/
│   └── pipeline_config.yaml    # Cấu hình ngưỡng cắt tiếng nói, tham số mô hình
├── src/
│   ├── crawler/                # Thu thập và trích xuất âm thanh từ liên kết
│   ├── separation/             # Tách giọng nói: demucs_engine.py và melband_engine.py
│   ├── vad_slicer/             # Cắt lát câu thoại bằng Silero VAD
│   ├── dedup/                  # Lọc trùng lặp âm thanh
│   ├── quality_gate/           # Đo lường tỷ lệ tín hiệu trên nhiễu và độ phẳng phổ
│   └── pipeline.py             # Kịch bản dòng lệnh chạy toàn bộ quy trình
├── scripts/
│   ├── run_demucs_pipeline.sh  # Kịch bản chạy nhánh Demucs
│   └── run_melband_pipeline.sh # Kịch bản chạy nhánh MelBand-RoFormer
├── tests/
│   └── test_pipeline.py        # Kiểm thử định dạng âm thanh, lọc trùng và chất lượng
├── requirements.txt            # Danh sách thư viện phụ thuộc
├── .gitignore
├── README.md                   # Hướng dẫn vận hành
└── SUMMARY.md                  # Báo cáo kỹ thuật và giải trình chi tiết
```

---

## ⚙️ 3. Yêu cầu môi trường và cài đặt

- **Hệ điều hành:** Linux Ubuntu 22.04/24.04, WSL2 hoặc Windows 11.
- **Python:** Phiên bản từ 3.10 trở lên.
- **Bộ xử lý đồ họa:** Card đồ họa NVIDIA tối thiểu 8 GB bộ nhớ (khuyến nghị RTX 3060, RTX 4090, A4000, phiên bản CUDA từ 12.1 trở lên).
- **Công cụ FFmpeg:** Đã cài đặt trên hệ thống (`sudo apt update && sudo apt install -y ffmpeg`).

### Cài đặt thư viện:
```bash
git clone https://github.com/conheo-map/ToolCrawl.git
cd ToolCrawl/speech_pipeline
pip install -r requirements.txt
```

---

## 🚀 4. Hướng dẫn vận hành nhanh

### Cách 1: Chạy với mô hình Demucs (tốc độ nhanh, xử lý số lượng lớn)
```bash
python src/pipeline.py --urls urls.txt --model demucs --output data/demucs_gold --device cuda
```

### Cách 2: Chạy với mô hình Mel-Band RoFormer (chất lượng âm thanh phòng thu)
```bash
python src/pipeline.py --urls urls.txt --model melband --output data/melband_gold --device cuda
```

### Giải thích các tham số dòng lệnh:
- `--urls`: Đường dẫn đến tệp văn bản chứa danh sách liên kết video (mỗi dòng một đường dẫn).
- `--model`: Lựa chọn mô hình tách nhạc (`demucs` hoặc `melband`).
- `--output`: Thư mục lưu kết quả đầu ra (tự động tạo thư mục chứa âm thanh sạch và tệp dữ liệu thông tin đi kèm).
- `--device`: Thiết bị tính toán (`cuda` hoặc `cpu`).
- `--limit`: Giới hạn số lượng liên kết cần xử lý để kiểm tra nhanh.

---

## 🧪 5. Kiểm thử mã nguồn

Chạy bộ kiểm thử tự động để đảm bảo hệ thống đạt chuẩn kỹ thuật trước khi xử lý dữ liệu lớn:
```bash
pytest -v tests/test_pipeline.py
```
*Kết quả: Toàn bộ các bài kiểm tra đều vượt qua, bao gồm kiểm tra định dạng âm thanh, thuật toán lọc trùng lặp và cổng kiểm soát chất lượng.*

---

## 💡 6. Hướng dẫn xử lý sự cố khi vận hành trên máy chủ đám mây

### 1. Tránh sự cố tràn bộ nhớ đồ họa
- Đối với các tệp âm thanh dài trên 5 phút, việc nạp toàn bộ vào bộ nhớ để xử lý cùng lúc có thể gây tràn bộ nhớ card đồ họa.
- **Giải pháp:** Hệ thống đã chia nhỏ âm thanh thành từng đoạn ngắn và chủ động thu hồi bộ nhớ ngay sau khi xử lý xong từng tệp.

### 2. Đồng bộ dữ liệu lên Google Drive từ máy chủ không có giao diện đồ họa
- Để đồng bộ kết quả trực tiếp lên Google Drive mà không cần trình duyệt:
  1. Khởi tạo cấu hình xác thực trên máy cá nhân.
  2. Sao chép nội dung tệp cấu hình vào đường dẫn `/root/.config/rclone/rclone.conf` trên máy chủ.
  3. Chạy lệnh đồng bộ đa luồng:
     ```bash
     rclone copy data/demucs_gold/gold_dataset "gdrive:Dataset/Week5/audio" --transfers 32 --checkers 64 -P
     ```
