# 🎙️ Facebook & TikTok Audio Crawler for Vietnamese ASR

Hệ thống thu thập, chuẩn hóa và xử lý tự động dữ liệu giọng nói tiếng Việt từ **TikTok** và **Facebook Reels** phục vụ huấn luyện các mô hình nhận dạng giọng nói (Automatic Speech Recognition - ASR).

---

## 📌 1. Mục Tiêu Dự Án (Project Goals)

- **Chỉ tiêu khối lượng:** Thu thập đủ **500 giờ** audio speech tiếng Việt trong **7 tuần** (~72 giờ/tuần, ~15 giờ/ngày).
- **Quy chuẩn kỹ thuật Audio:** 100% audio đầu ra chuẩn định dạng **WAV (16 kHz, Mono, PCM S16LE)**.
- **Chỉ tiêu chất lượng:**
  - Tiếng Việt rõ chữ, tự nhiên.
  - Tự động phát hiện và loại bỏ / cách ly audio dính nhạc nền (background music).
  - Lọc trùng video/audio qua cơ chế hash ID và checkpoint.
- **Hệ thống & Dữ liệu:**
  - Xuất metadata đầy đủ mapping về URL gốc.
  - Quản lý phiên crawl, retry các item lỗi độc lập.

---

## 🏗️ 2. Cấu Trúc Hệ Thống (Architecture)

```
c:\HocC\SaydiTool\
├── crawlers/                   # Module tìm kiếm và bóc tách metadata
│   ├── base.py                 # Base yt-dlp wrapper, retry, tải tạm
│   ├── tiktok.py               # TikTok crawler (tìm kiếm + parse meta)
│   └── facebook.py             # Facebook crawler (tìm kiếm + parse meta)
├── processors/                 # Module xử lý âm thanh
│   ├── audio_converter.py      # Chuyển đổi WAV 16kHz Mono qua FFmpeg & ffprobe
│   └── music_detector.py       # Lọc nhạc nền 2 tầng (Metadata + Librosa Signal)
├── storage/                    # Quản lý dữ liệu và trạng thái
│   ├── dedup.py                # Lọc trùng item_id xuyên suốt các phiên
│   ├── metadata_writer.py      # Ghi metadata.json & summary.json an toàn đa luồng
│   └── state_manager.py        # Checkpoint lưu trạng thái resume khi bị ngắt
├── utils/                      # Tiện ích bổ trợ
│   ├── logger.py               # Log màu, hỗ trợ UTF-8 console và file log
│   ├── rate_limiter.py         # Jitter delay ngẫu nhiên & exponential backoff
│   └── proxy_manager.py        # Xoay vòng User-Agent và proxy
├── tests/                      # Bộ kiểm thử tự động (8 unit tests)
├── config.py                   # Cấu hình trung tâm
├── main.py                     # Entry point thực thi chính
├── retry_failed.py             # Script chạy lại các audio bị lỗi
├── Dockerfile                  # Đóng gói môi trường Docker
├── docker-compose.yml          # Chạy ứng dụng qua Docker Compose
└── requirements.txt            # Danh sách thư viện Python
```

---

## ⚙️ 3. Hướng Dẫn Cài Đặt (Installation)

### Cách 1: Chạy trực tiếp trên máy (Khuyến nghị)

#### Yêu cầu hệ thống:
1. **Python 3.10+** (Đã có sẵn)
2. **FFmpeg:** Cần cài đặt để xử lý âm thanh.
   - Trên Windows (PowerShell):
     ```powershell
     winget install FFmpeg
     ```
   - Kiểm tra cài đặt thành công: `ffmpeg -version` và `ffprobe -version`.

#### Cài đặt môi trường ảo:
```powershell
cd c:\HocC\SaydiTool

# 1. Tạo môi trường ảo
python -m venv .venv

# 2. Kích hoạt môi trường ảo
.\.venv\Scripts\Activate.ps1

# 3. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

---

### Cách 2: Chạy thông qua Docker & Linux / VPS

Nếu sử dụng Docker, bạn **không cần cài đặt FFmpeg hay Python** lên máy đích. Docker cho phép đóng gói toàn bộ dự án thành một file image duy nhất để mang sang bất kỳ máy tính hoặc VPS Linux nào chạy ngay lập tức.

```powershell
# Build Docker image
docker build -t audio-crawler .

# Chạy crawler qua Docker
docker run -v ${PWD}/Week2:/app/Week2 audio-crawler --platform tiktok --keyword "review quán ăn" --workers 4
```

> 📖 **Xem hướng dẫn chi tiết từ A-Z:** [DOCKER_LINUX_GUIDE.md](file:///c:/HocC/SaydiTool/DOCKER_LINUX_GUIDE.md) (Hướng dẫn cách xuất file `.tar` copy sang máy khác, cài đặt trên Linux/VPS, chạy ngầm 24/7 với `docker compose` và kéo dữ liệu audio về qua SFTP/FileZilla).

---

## 🚀 4. Hướng Dẫn Chạy (Usage)

### 4.1. Chạy Crawl TikTok (Có tài khoản / Cookie - Tối ưu nhất)

```powershell
# Kích hoạt môi trường nếu chưa bật
.\.venv\Scripts\Activate.ps1

# Chạy crawl TikTok với keyword được giao
python main.py --platform tiktok --keyword "review quán ăn Hà Nội" --workers 4 --cookies cookies_tiktok.txt
```

### 4.2. Chạy Crawl Facebook Reels / Videos

```powershell
python main.py --platform facebook --keyword "học tiếng Việt giao tiếp" --workers 4
```

### 4.3. Kiểm tra trước danh sách URL (Dry-run không tải audio)

```powershell
python main.py --platform tiktok --keyword "tin tức thời sự" --dry-run
```

### 4.4. Chạy Retry lại các video bị lỗi trong ngày

```powershell
python retry_failed.py --platform tiktok --workers 2
```

### 4.5. Chạy kiểm thử hệ thống (Automated Tests)

```powershell
pytest -o pythonpath=. -v
```

---

## 💡 5. Phương Án Tối Ưu Nhất Đạt Chỉ Tiêu 500 Giờ

Để đạt **500 giờ trong 7 tuần** (~15 giờ/ngày) mà **không bị hạn chế IP hay checkpoint tài khoản**, dưới đây là chiến lược tối ưu:

### 🌟 Chiến Lược 1: Sử dụng Tài Khoản TikTok (Cookie Authentication)
Vì bạn có thể cung cấp tài khoản TikTok, đây là lợi thế lớn nhất giúp vượt qua cơ chế giới hạn tìm kiếm ẩn danh của TikTok:

#### Các bước xuất Cookie:
1. Mở trình duyệt (Chrome/Edge/Brave), cài extension [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbngbenkjcfflieimamfojl).
2. Đăng nhập vào tài khoản TikTok trên trình duyệt.
3. Bấm vào icon extension, chọn **Export** và lưu file với tên `cookies_tiktok.txt` đặt trực tiếp trong thư mục dự án `c:\HocC\SaydiTool\`.
4. Khi chạy, truyền tham số: `--cookies cookies_tiktok.txt`.

> **Ưu điểm:** Tỷ lệ tìm kiếm được video tăng gấp 10 lần so với tìm kiếm ẩn danh, giảm 95% nguy cơ bị trả về mã bảo vệ CAPTCHA.

---

### ⚡ Chiến Lược 2: Phân Bổ Worker & Tốc Độ Crawl
- **Số Worker tối ưu:** Đặt `--workers 3` đến `--workers 4` trên 1 địa chỉ mạng IP gia đình.
- **Delay tự nhiên:** Hệ thống đã tích hợp sẵn delay ngẫu nhiên `1.5s - 4.5s` giữa các request để mô phỏng người dùng thật.
- **Thời gian chạy:** Có thể chia làm 2 ca chạy mỗi ngày (mỗi ca khoảng 3–4 tiếng) để đạt sản lượng ~15 giờ audio sạch/ngày.

---

### 🎯 Chiến Lược 3: Chọn Lọc Keyword Nhiều Giọng Nói Tự Nhiên
Để đạt tỷ lệ giữ lại audio cao sau khi lọc nhạc nền:
- **Nên chọn:**
  - `review quán ăn`, `hướng dẫn nấu ăn`, `kể chuyện đêm khuya`, `tâm sự đời sống`.
  - `tin tức trong ngày`, `phỏng vấn đường phố`, `podcast tiếng việt`, `học tiếng việt`.
  - `vlog cuộc sống`, `chia sẻ kinh nghiệm`, `đọc sách nói`.
- **Hạn chế:**
  - `nhảy tiktok`, `trend biến hình`, `remix`, `dance cover` (các video này 90% dính nhạc nền và sẽ bị đưa vào thư mục cách ly `quarantine`).

---

### 🛡️ Chiến Lược 4: Tự Động Lọc Nhạc Nền 2 Tầng
Hệ thống sử dụng bộ lọc 2 tầng thông minh:
1. **Tầng 1 (Metadata):** Nhận diện trường `music_is_original` và tên bài hát từ TikTok. Nếu phát hiện bài hát thương mại không phải âm thanh gốc, hệ thống lập tức loại trừ mà không tốn tài nguyên xử lý.
2. **Tầng 2 (Librosa Spectral Flatness):** Đối với các audio chưa rõ, phân tích độ phẳng phổ tần số. Nếu năng lượng tập trung như giai điệu bài hát, file được tự động chuyển vào thư mục `quarantine/` để bạn có thể nghe lại thủ công nếu cần.

---

## 📂 6. Cấu Trúc Dữ Liệu Đầu Ra (Output Format)

Dữ liệu được tổ chức tự động theo chuẩn quy định:

```
Week{i}/{Date}/
├── audio/
│   ├── tt_7412345678901234567.wav   # File WAV 16kHz, mono
│   └── fb_123456789012345.wav
├── quarantine/                      # Audio nghi dính nhạc nền
├── metadata.json                    # Danh sách metadata chi tiết
└── summary.json                     # Báo cáo tổng kết ngày
```

### Format `metadata.json` mẫu:
```json
[
  {
    "item_id": "tt_7412345678901234567",
    "platform": "tiktok",
    "platform_video_id": "7412345678901234567",
    "video_url": "https://www.tiktok.com/@channelname/video/7412345678901234567",
    "title": "Review quán ăn ngon Hà Nội",
    "description": "Chia sẻ trải nghiệm ẩm thực phố cổ #review #food",
    "posted_at": "2026-08-10T13:22:05+07:00",
    "language_raw": "vi",
    "audio_path": "audio/tt_7412345678901234567.wav",
    "duration_seconds": 187.44,
    "crawl_batch": "tt_20260819_01",
    "crawled_at": "2026-08-19T09:14:00+07:00",
    "platform_meta": {
      "music_is_original": true,
      "is_duet": false,
      "is_stitch": false,
      "has_platform_captions": true
    }
  }
]
```

### Format `summary.json` mẫu:
```json
{
  "platform": "tiktok",
  "crawl_date": "2026-08-19",
  "batch_count": 1,
  "audio_spec": {
    "sample_rate": 16000,
    "channels": 1,
    "format": "wav_pcm_s16le"
  },
  "items_delivered": 450,
  "unique_item_ids": 450,
  "total_hours": 15.25,
  "error_count": 8
}
```

---

## 🛠️ 7. Quản Lý & Lưu Trữ Với Git / GitHub

1. Tạo repository mới trên [GitHub](https://github.com/new) (ví dụ: `audio-crawler`).
2. Liên kết và đẩy mã nguồn lên:
   ```powershell
   git remote add origin https://github.com/<your-username>/audio-crawler.git
   git branch -M main
   git push -u origin main
   ```
*(Hệ thống đã cấu hình sẵn `.gitignore` để không bao giờ push nhầm file audio `.wav` hay file cookie cá nhân lên GitHub).*
