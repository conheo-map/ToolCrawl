# 🎙️ Hệ thống xử lý dữ liệu âm thanh tiếng nói

> **Hệ thống thu thập, tách nguồn âm thanh độc lập bằng Demucs và Mel-Band RoFormer, cắt lát giọng nói Silero VAD và lọc trùng lặp chuẩn hóa dữ liệu huấn luyện nhận dạng và tổng hợp tiếng nói.**

---

## 📌 1. Giới thiệu dự án

Kho mã nguồn chuẩn hóa toàn diện quy trình xử lý dữ liệu âm thanh từ các nền tảng mạng xã hội như TikTok, Facebook Reels, YouTube Shorts hoặc từ các tệp âm thanh thô thành tập dữ liệu sạch đạt chuẩn vàng, sẵn sàng nạp trực tiếp vào các mô hình huấn luyện tiếng nói như Whisper, Conformer hoặc VITS.

### 🎯 Chuẩn dữ liệu đầu ra
- **Định dạng âm thanh:** WAV 16.000 Hz, kênh đơn, 16-bit PCM.
- **Mức âm lượng chuẩn hóa:** Chuẩn hóa âm lượng mức -20 LUFS.
- **Độ dài phân đoạn:** Từ 3,0 đến 15,0 giây, cắt tự nhiên theo biên giới câu nói bằng thuật toán nhận diện hoạt tính giọng nói Silero VAD.
- **Tệp thông tin đi kèm (`metadata.jsonl`):**
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
    "processed_at": "2026-09-18T00:00:00"
  }
  ```

---

## 🏗️ 2. Cấu trúc mã nguồn

```text
speech_pipeline/
├── configs/
│   └── pipeline_config.yaml    # Cấu hình ngưỡng cắt tiếng nói, tham số mô hình
├── src/
│   ├── crawler/                # Thu thập âm thanh qua TikWM API & yt-dlp
│   ├── separation/             # Tách giọng nói: demucs_engine.py và melband_engine.py
│   ├── vad_slicer/             # Cắt lát câu thoại bằng Silero VAD (3s - 15s)
│   ├── dedup/                  # Lọc trùng lặp bằng dấu vân tay sóng âm SHA-256
│   ├── quality_gate/           # Đo lường tỷ lệ tín hiệu trên nhiễu và độ phẳng phổ
│   └── pipeline.py             # Kịch bản dòng lệnh tích hợp toàn trình
├── scripts/
│   ├── run_demucs_pipeline.sh  # Kịch bản chạy nhánh Demucs
│   └── run_melband_pipeline.sh # Kịch bản chạy nhánh Mel-Band RoFormer
├── tests/
│   └── test_pipeline.py        # Bộ kiểm thử tự động đạt chuẩn kỹ thuật
├── requirements.txt            # Danh sách thư viện phụ thuộc
├── .gitignore
├── README.md                   # Hướng dẫn cài đặt và vận hành
└── SUMMARY.md                  # Báo cáo kỹ thuật và giải trình chi tiết
```

---

## ⚙️ 3. Yêu cầu môi trường và hướng dẫn cài đặt

### Yêu cầu hệ thống:
- **Hệ điều hành:** Linux Ubuntu 22.04/24.04, WSL2, hoặc Windows 11.
- **Python:** Phiên bản từ 3.10 trở lên.
- **Phần cứng:** Khuyến nghị có card đồ họa NVIDIA tối thiểu 4 GB đến 8 GB bộ nhớ (như RTX 2050, RTX 3060, RTX 4090, A4000, phiên bản CUDA từ 12.1 trở lên). Vẫn hỗ trợ chế độ chỉ dùng CPU.
- **Công cụ FFmpeg:** Cần cài đặt sẵn trên hệ thống.

---

### Các bước cài đặt chi tiết:

#### Bước 1: Kéo kho mã nguồn về máy
```bash
git clone https://github.com/conheo-map/ToolCrawl.git
cd ToolCrawl
```

#### Bước 2: Cài đặt công cụ xử lý đa phương tiện FFmpeg
- **Trên Linux / Ubuntu / Máy chủ RunPod:**
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```
- **Trên Windows:**
  Cài đặt nhanh qua trình quản lý gói của Windows:
  ```powershell
  winget install Gyan.FFmpeg
  ```
  *(Hoặc tải tệp zip từ trang chủ FFmpeg và thêm vào biến môi trường Path).*

#### Bước 3: Tạo môi trường ảo và cài đặt thư viện phụ thuộc
- **Trên Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r speech_pipeline/requirements.txt
  ```
- **Trên Linux / macOS / RunPod:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r speech_pipeline/requirements.txt
  ```

---

## 🚀 4. Hướng dẫn vận hành

### Bước 1: Chuẩn bị tệp danh sách đầu vào (`urls.txt`)
Tạo một tệp văn bản (ví dụ `urls.txt` hoặc `url.txt`), bên trong chứa các đường link video hoặc đường dẫn tệp âm thanh có sẵn trên máy (mỗi dòng một đường dẫn):

```text
https://www.tiktok.com/@vtv24news/video/7408796515814526216
sample_human_speech.wav
```

---

### Bước 2: Chạy xử lý dữ liệu qua dòng lệnh

#### 🔹 Cách 1: Chạy với mô hình Demucs (Tốc độ cao, tối ưu thông lượng lớn)
```bash
python speech_pipeline/src/pipeline.py --urls urls.txt --model demucs --output data/demucs_gold --device cuda
```

#### 🔹 Cách 2: Chạy với mô hình Mel-Band RoFormer (Chất lượng âm thanh phòng thu)
```bash
python speech_pipeline/src/pipeline.py --urls urls.txt --model melband --output data/melband_gold --device cuda
```

#### 🔹 Cách 3: Chạy trên máy chỉ có CPU (Không có card đồ họa rời)
```bash
python speech_pipeline/src/pipeline.py --urls urls.txt --model demucs --output data/demucs_gold --device cpu
```

#### 🔹 Cách 4: Chạy thử nghiệm nhanh giới hạn số lượng video
```bash
python speech_pipeline/src/pipeline.py --urls urls.txt --model demucs --output data/test_run --device cuda --limit 5
```

---

## 📋 5. Bảng giải thích chi tiết các cờ và tham số dòng lệnh

| Tên cờ (Tham số) | Viết tắt | Kiểu giá trị | Bắt buộc | Giá trị mặc định | Giải thích chi tiết |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `--urls` | `-u` | Chuỗi ký tự | **Có** | *Không có* | Đường dẫn đến tệp danh sách liên kết video (`urls.txt`, `url.txt`) hoặc đường dẫn tệp âm thanh trên máy. |
| `--model` | `-m` | `demucs` hoặc `melband` | Không | `demucs` | Lựa chọn mô hình tách nhạc nền: <br>• `demucs`: Xử lý cực nhanh, tối ưu tài nguyên. <br>• `melband`: Tách giọng nói chất lượng cao nhất, đa ca lấy mẫu. |
| `--output` | `-o` | Chuỗi ký tự | **Có** | *Không có* | Thư mục lưu trữ kết quả đầu ra (hệ thống tự động tạo thư mục `gold_dataset/` và tệp `metadata.jsonl`). |
| `--device` | `-d` | `cuda` hoặc `cpu` | Không | `cuda` (nếu có) | Thiết bị tính toán: chọn `cuda` để chạy bằng card đồ họa NVIDIA hoặc `cpu` nếu chạy trên chip xử lý chính. |
| `--limit` | `-l` | Số nguyên | Không | `0` (tất cả) | Giới hạn số lượng liên kết cần xử lý trong tệp danh sách, phù hợp khi cần chạy thử nghiệm nhanh một vài mẫu. |

---

## 🧪 6. Kiểm thử mã nguồn tự động

Chạy bộ kiểm thử tự động để đảm bảo hệ thống đạt 100% tiêu chuẩn kỹ thuật:
```bash
pytest -v speech_pipeline/tests/test_pipeline.py
```
*Kết quả kiểm thử: Đạt chuẩn 3/3 bài kiểm tra vượt qua, bao gồm kiểm tra định dạng âm thanh 16 kHz Mono PCM16, thuật toán lọc trùng lặp sóng âm và cổng kiểm soát chất lượng.*

---

## 💡 7. Cẩm nang xử lý sự cố khi vận hành

### 1. Tránh sự cố tràn bộ nhớ đồ họa khi xử lý tệp dài
- Đối với các tệp âm thanh dài trên 5 phút, việc nạp toàn bộ vào bộ nhớ để xử lý cùng lúc có thể gây tràn bộ nhớ card đồ họa.
- **Giải pháp:** Hệ thống đã chia nhỏ âm thanh thành từng đoạn ngắn và chủ động thu hồi bộ nhớ qua lệnh `torch.cuda.empty_cache()` ngay sau khi xử lý xong từng tệp.

### 2. Tránh bị chặn IP khi cào dữ liệu
- Hệ thống đã tích hợp sẵn cơ chế gọi trực tiếp qua máy chủ trung gian để lấy luồng video gốc, loại bỏ hoàn toàn hiện tượng bị chặn IP mạng cá nhân và tránh lấy nhầm nhạc nền từ kho thư viện.

### 3. Đồng bộ dữ liệu lên Google Drive từ máy chủ không có giao diện
- Để đồng bộ kết quả trực tiếp lên Google Drive từ máy chủ đám mây:
  1. Khởi tạo cấu hình xác thực trên máy cá nhân để lấy tệp `rclone.conf`.
  2. Sao chép nội dung vào đường dẫn `/root/.config/rclone/rclone.conf` trên máy chủ.
  3. Chạy lệnh đồng bộ đa luồng:
     ```bash
     rclone copy data/demucs_gold/gold_dataset "gdrive:Dataset/Week5/audio" --transfers 32 --checkers 64 -P
     ```
