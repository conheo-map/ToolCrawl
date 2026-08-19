# 🎙️ SAYDITOOL — VIETNAMESE SPEECH AUDIO CRAWLER & AI PIPELINE
> **Dự án:** Hệ thống Thu thập & Xử lý Dữ liệu Âm thanh Tiếng Việt quy mô lớn cho huấn luyện nhận dạng giọng nói (Vietnamese ASR Dataset Pipeline).  
> **Mục tiêu:** Thu thập 500 giờ âm thanh chuẩn ASR trong 7 tuần từ Facebook Reels & TikTok.  
> **Phiên bản:** 2.0 (Tích hợp Pipeline Hybrid Tách Giọng & Khử Nhạc AI).

---

## 🧭 HƯỚNG DẪN NHẬN BIẾT MÔI TRƯỜNG & TERMINAL SỬ DỤNG
Trước khi chạy bất kỳ câu lệnh nào, hãy chú ý **Biểu tượng & Loại Terminal** được ghi chú ở từng khối lệnh:

| Biểu tượng | Loại Terminal / Môi trường | Cách mở đúng |
|---|---|---|
| 🔵 **[PowerShell - Thư mục Dự án]** | Windows PowerShell tại `C:\HocC\SaydiTool` | Mở File Explorer vào `C:\HocC\SaydiTool`, bấm vào thanh địa chỉ gõ `powershell` rồi gõ Enter (Hiện dòng nhắc: `PS C:\HocC\SaydiTool>`) |
| 🛡️ **[PowerShell - Administrator]** | Windows PowerShell quyền Quản trị | Bấm phím `Windows` -> gõ `powershell` -> Click chuột phải chọn **Run as Administrator** (Dùng khi cài phần mềm) |
| 🐧 **[Linux - WSL 2 Ubuntu]** | Terminal Linux Ubuntu | Mở ứng dụng **Ubuntu** từ Start Menu, hoặc từ PowerShell gõ `wsl` (Hiện dòng nhắc: `user@machine:/mnt/c/HocC/SaydiTool$`) |
| 🌐 **[GitHub Web Browser]** | Trình duyệt Web | Thao tác trên giao diện website `github.com` |

---

## 📑 MỤC LỤC
1. [Cấu trúc Thư mục & Vai trò từng Module](#1-cấu-trúc-thư-mục--vai-trò-từng-module)
2. [Thông số Kỹ thuật Âm thanh & Chuẩn Dữ liệu](#2-thông-số-kỹ-thuật-âm-thanh--chuẩn-dữ-liệu)
3. [Công cụ & Thư viện Sử dụng](#3-công-cụ--thư-viện-sử-dụng)
4. [Hướng dẫn Cài đặt Môi trường từ Số 0](#4-hướng-dẫn-cài-đặt-môi-trường-từ-số-0)
5. [Hướng dẫn Lấy Cookies & Chuẩn bị Danh sách Link](#5-hướng-dẫn-lấy-cookies--chuẩn-bị-link)
6. [Quy trình Vận hành Crawler Chi tiết](#6-quy-trình-vận-hành-crawler-chi-tiết)
7. [Pipeline Hybrid 3 Tầng: Tách Giọng & Khử Nhạc AI](#7-pipeline-hybrid-3-tầng-tách-giọng--khử-nhạc-ai)
8. [Đóng gói Docker & Chạy trên Máy tính khác](#8-đóng-gói-docker--chạy-trên-máy-tính-khác)
9. [Đẩy lên GitHub & Cào Cloud Miễn Phí bằng GitHub Actions](#9-đẩy-lên-github--cào-cloud-miễn-phí-bằng-github-actions)
10. [Đồng bộ Dữ liệu sang Google Drive với Rclone](#10-đồng-bộ-dữ-liệu-sang-google-drive-với-rclone)
11. [Bảng Tra cứu Toàn bộ Câu Lệnh (Cheatsheet)](#11-bảng-tra-cứu-toàn-bộ-câu-lệnh-cheatsheet)
12. [Cẩm nang Xử lý Sự cố & Debug Lỗi (Troubleshooting)](#12-cẩm-nang-xử-lý-sự-cố--debug-lỗi-troubleshooting)

---

## 1. CẤU TRÚC THƯ MỤC & VAI TRÒ TỪNG MODULE

Dự án được tổ chức theo kiến trúc phân tầng sạch sẽ (Clean Modular Architecture):

```text
SaydiTool/
├── .github/workflows/          # [Cloud CI/CD] Tự động cào đám mây không tốn ổ đĩa
│   └── cloud_crawler.yml       # Workflow GitHub Actions tự động đẩy Google Drive
├── crawlers/                   # [Module Cào Dữ Liệu - yt-dlp & Network]
│   ├── __init__.py
│   ├── base.py                 # BaseCrawler: tải video, convert WAV, retry, backoff, temp cookies
│   ├── facebook.py             # FacebookCrawler: bóc tách HTML regex Facebook Reels & Videos
│   └── tiktok.py               # TikTokCrawler: xử lý video, channel, cookie impersonation
├── processors/                 # [Module Xử Lý Âm Thanh - Audio Engineering & AI]
│   ├── __init__.py
│   ├── audio_converter.py      # Chuyển đổi định dạng WAV 16kHz Mono bằng FFmpeg & ffprobe
│   ├── music_detector.py       # Bộ phát hiện nhạc nền 2 tầng (Metadata Heuristic + Librosa)
│   └── vocal_separator.py      # Bộ tách giọng AI (Meta Demucs + Spectral Noise Gating)
├── storage/                    # [Module Quản Lý Dữ Liệu & Lưu Trữ]
│   ├── __init__.py
│   ├── dedup.py                # Thread-safe ID deduplication (chống cào trùng lặp)
│   ├── metadata_writer.py      # Ghi metadata.json & summary.json chuẩn JSON schema
│   └── state_manager.py        # Checkpoint lưu trạng thái resume khi gặp sự cố
├── utils/                      # [Module Tiện Ích Chung]
│   ├── __init__.py
│   ├── logger.py               # Ghi log đa màu sắc, chuẩn UTF-8 Windows
│   ├── proxy_manager.py        # Quản lý User-Agent rotation & Proxy list
│   └── rate_limiter.py         # Điều tiết tốc độ request với Random Jitter & Exponential Backoff
├── tests/                      # [Bộ Kiểm Thử Tự Động] 10 unit tests bao phủ 100% core logic
│   ├── test_audio_converter.py
│   ├── test_crawler_parsing.py
│   ├── test_dedup.py
│   ├── test_metadata_writer.py
│   ├── test_music_detector.py
│   ├── test_state_manager.py
│   └── test_vocal_separator.py
├── docs/                       # [Tài Liệu Hướng Dẫn]
│   └── MASTER_GUIDE.md         # Bản sao lưu tài liệu toàn tập
├── Week2/                      # Thư mục chứa dữ liệu đầu ra theo tuần
│   └── YYYY-MM-DD/             # Dữ liệu theo ngày cào (VD: 2026-08-19)
│       ├── audio/              # File âm thanh WAV sạch đạt chuẩn huấn luyện ASR
│       ├── quarantine/         # File audio cách ly (nếu không tách được nhạc)
│       ├── metadata.json       # Metadata chi tiết từng file
│       └── summary.json        # Thống kê tổng hợp số lượng & tổng số giờ
├── .checkpoints/               # Checkpoint lưu trạng thái chạy
├── errors/                     # Log lỗi chi tiết (failed_YYYY-MM-DD.jsonl)
├── logs/                       # Log thực thi hệ thống (crawler.log)
├── config.py                   # Cấu hình trung tâm (tuần, sample rate, rate limit, timeout)
├── main.py                     # CLI Entry Point chính của toàn bộ dự án
├── retry_failed.py             # Script tự động thử lại các URL bị lỗi
├── urls.txt                    # File chứa danh sách link cần cào hàng loạt
├── cookies_tiktok.txt          # Cookie Netscape format cho TikTok
├── Dockerfile                  # Cấu hình đóng gói Docker container
├── docker-compose.yml          # Cấu hình chạy ngầm Docker Compose
├── requirements.txt            # Danh sách thư viện Python
└── README.md                   # Tài liệu chính của dự án
```

---

## 2. THÔNG SỐ KỸ THUẬT ÂM THANH & CHUẨN DỮ LIỆU

### 🎯 Chuẩn đầu ra Audio (ASR Standard):
- **Định dạng:** WAV PCM 16-bit Little Endian (`pcm_s16le`).
- **Sample Rate:** `16,000 Hz` (16 kHz).
- **Kênh:** `1 Channel` (Mono).
- **Thời lượng:** `5.0s` đến `600.0s` (10 phút).
- **Tên file:** `{item_id}.wav` (VD: `tt_7675666420574735634.wav`, `fb_1410384157640503.wav`).

### 📄 Cấu trúc `metadata.json`:
```json
[
  {
    "item_id": "tt_7675666420574735634",
    "platform": "tiktok",
    "platform_video_id": "7675666420574735634",
    "video_url": "https://www.tiktok.com/@kienthuckinhte28/video/7675666420574735634",
    "title": "Từ một tờ tiền 500.000 vnđ...",
    "description": "Từ một tờ tiền 500.000 vnđ...",
    "posted_at": "2026-08-19T16:35:41+07:00",
    "language_raw": "vi",
    "audio_path": "audio/tt_7675666420574735634.wav",
    "duration_seconds": 101.542,
    "crawl_batch": "tt_20260819_01",
    "crawled_at": "2026-08-19T18:50:25+07:00",
    "platform_meta": {
      "music_is_original": false,
      "is_duet": false,
      "is_stitch": false,
      "has_platform_captions": false
    },
    "vocal_separated": true,
    "clean_method": "demucs_ai"
  }
]
```

### 📊 Cấu trúc `summary.json`:
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
  "items_delivered": 100,
  "unique_item_ids": 100,
  "vocal_separated_count": 88,
  "total_hours": 3.25,
  "error_count": 0
}
```

---

## 3. CÔNG CỤ & THƯ VIỆN SỬ DỤNG

| Công nghệ | Phiên bản | Vai trò trong hệ thống |
|---|---|---|
| **Python** | 3.12 / 3.13 | Nền tảng lập trình chính |
| **FFmpeg & ffprobe** | 6.x / 7.x | Chuyển đổi định dạng audio sang 16kHz mono & kiểm tra thông số |
| **yt-dlp** | `2026.7.4+` | Download video chất lượng cao từ TikTok & Facebook |
| **curl-cffi** | `0.15.0+` | Giả lập TLS fingerprint của Chrome 131 chống chặn bot |
| **Librosa** | `0.10.0+` | Phân tích tín hiệu âm thanh, Spectral Flatness, Harmonic-Percussive separation |
| **noisereduce** | `3.0.3+` | Khử nhạc nền, lọc tiếng ồn phổ với tốc độ 1-2s và 0 MB disk |
| **Demucs** | `4.1.0+` | Mô hình Deep Learning của Meta Research bóc tách track Vocals chuyên sâu |
| **Docker & Compose** | 29.x | Đóng gói toàn bộ ứng dụng chạy độc lập trên mọi hệ điều hành |
| **WSL 2 (Ubuntu)** | 2.x | Môi trường Linux tích hợp trong Windows |
| **Git & GitHub** | 2.x | Quản lý phiên bản mã nguồn |
| **Rclone** | 1.66+ | Đồng bộ dữ liệu âm thanh tự động lên Google Drive |

---

## 4. HƯỚNG DẪN CÀI ĐẶT MÔI TRƯỜNG TỪ SỐ 0

### 🖥️ 4.1. Cài đặt trên Windows (Host)

> 🛡️ **[Chạy trên: PowerShell Administrator]**  
> Bấm phím Windows -> gõ `powershell` -> Click chuột phải chọn **Run as Administrator**:

```powershell
# Cài đặt FFmpeg qua winget:
winget install Gyan.FFmpeg

# Kiểm tra FFmpeg đã nhận chưa:
ffmpeg -version
```

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**  
> Mở PowerShell và di chuyển vào thư mục dự án:

```powershell
# 1. Chuyển vào đúng thư mục dự án:
cd C:\HocC\SaydiTool

# 2. Tạo môi trường ảo .venv:
python -m venv .venv

# 3. Kích hoạt môi trường ảo:
.\.venv\Scripts\Activate.ps1
# (Sau khi kích hoạt, đầu dòng lệnh sẽ hiện chữ (.venv))

# 4. Cài đặt toàn bộ thư viện:
pip install -r requirements.txt
```

---

### 🐳 4.2. Cài đặt Docker & WSL 2 Linux

> 🛡️ **[Chạy trên: PowerShell Administrator]**:

```powershell
# Cài đặt WSL 2 với bản phân phối Ubuntu:
wsl --install -d Ubuntu
# (Khởi động lại máy tính nếu Windows yêu cầu)
```

1. **Cài Docker Desktop:** Tải bộ cài từ `docker.com/products/docker-desktop` và cài đặt.
   - Trong quá trình cài: Tích chọn **Use WSL 2 instead of Hyper-V**.
   - Mở app Docker Desktop -> Nhấn vào biểu tượng bánh răng **Settings** -> **Resources** -> **WSL Integration** -> Bật nút gạt ở mục **Ubuntu** -> Bấm **Apply & Restart**.

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**:

```powershell
# Kiểm tra Docker đã chạy thành công chưa:
docker --version
docker ps
```

---

## 5. HƯỚNG DẪN LẤY COOKIES & CHUẨN BỊ LINK

### 🍪 5.1. Xuất file `cookies_tiktok.txt`:
1. Dùng trình duyệt Chrome, cài tiện ích: **Get cookies.txt LOCALLY**.
2. Đăng nhập vào trang `tiktok.com`.
3. Bấm vào icon tiện ích -> Chọn định dạng **Netscape** -> Nhấn **Export**.
4. Lưu file với tên `cookies_tiktok.txt` vào thư mục dự án `C:\HocC\SaydiTool\cookies_tiktok.txt`.

### 📝 5.2. Chuẩn bị file [`urls.txt`](file:///c:/HocC/SaydiTool/urls.txt):
Mở file `urls.txt` trong thư mục dự án và dán các link video cần cào (mỗi dòng 1 link):
```text
https://www.tiktok.com/@kienthuckinhte28/video/7675666420574735634
https://www.tiktok.com/@vtv24news/video/7391234567890123456
https://www.facebook.com/reel/1410384157640503
https://www.facebook.com/watch?v=1039665577514847
```

---

## 6. QUY TRÌNH VẬN HÀNH CRAWLER CHI TIẾT

### 👉 Cách 1: Chạy trực tiếp bằng Python (.venv) — *Khuyên dùng hàng ngày*

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**:

```powershell
# 1. Chuyển vào thư mục dự án:
cd C:\HocC\SaydiTool

# 2. Kích hoạt môi trường ảo:
.\.venv\Scripts\Activate.ps1

# 3. Cào toàn bộ danh sách trong file urls.txt (Có tự động tách nhạc):
python main.py --platform tiktok --keyword "urls.txt" --cookies cookies_tiktok.txt --workers 4

# 4. Cào Facebook theo từ khóa tìm kiếm:
python main.py --platform facebook --keyword "học tiếng Việt" --workers 4

# 5. Cào toàn bộ video từ 1 kênh TikTok cụ thể:
python main.py --platform tiktok --keyword "https://www.tiktok.com/@vtv24news" --cookies cookies_tiktok.txt --workers 4

# 6. Chạy thử nghiệm xem danh sách link, không tải file (Dry Run):
python main.py --platform facebook --keyword "học tiếng Việt" --dry-run
```

---

### 👉 Cách 2: Chạy bằng Docker Container

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**:

```powershell
# 1. Chuyển vào thư mục dự án:
cd C:\HocC\SaydiTool

# 2. Build image Docker (Chỉ làm lần đầu hoặc khi sửa code):
docker build -t audio-crawler .

# 3. Chạy cào TikTok mount thư mục đầu ra Week2:
docker run --rm `
  -v ${PWD}/Week2:/app/Week2 `
  -v ${PWD}/urls.txt:/app/urls.txt `
  -v ${PWD}/cookies_tiktok.txt:/app/cookies_tiktok.txt `
  audio-crawler `
  --platform tiktok `
  --keyword "urls.txt" `
  --cookies cookies_tiktok.txt `
  --workers 4

# 4. Chạy nền 24/7 bằng Docker Compose:
docker compose up -d

# Xem log chạy ngầm thời gian thực:
docker compose logs -f

# Dừng container chạy ngầm:
docker compose down
```

---

### 👉 Cách 3: Chạy trên Linux (WSL 2 Ubuntu)

> 🐧 **[Chạy trên: Terminal Linux Ubuntu]**  
> Mở Ubuntu Terminal từ Start Menu hoặc gõ `wsl` trong PowerShell:

```bash
# 1. Chuyển vào thư mục dự án trên Windows mount qua /mnt/c:
cd /mnt/c/HocC/SaydiTool

# 2. Chạy container bằng Docker trên Linux:
docker run --rm \
  -v $(pwd)/Week2:/app/Week2 \
  -v $(pwd)/urls.txt:/app/urls.txt \
  -v $(pwd)/cookies_tiktok.txt:/app/cookies_tiktok.txt \
  audio-crawler \
  --platform tiktok \
  --keyword "urls.txt" \
  --cookies cookies_tiktok.txt \
  --workers 4
```

---

## 7. PIPELINE HYBRID 3 TẦNG: TÁCH GIỌNG & KHỬ NHẠC AI

Để giải quyết triệt để vấn đề **90% video TikTok dính nhạc nền**, hệ thống tự động xử lý theo mô hình 3 tầng:

```mermaid
graph TD
    A[Video TikTok / Facebook Tải Về] --> B[FFmpeg Convert WAV 16kHz Mono]
    B --> C{MusicDetector: Kiểm tra Nhạc Nền?}
    C -- Âm thanh Gốc Sạch --> D[Tầng 1: Lưu thẳng audio/ + vocal_separated: false]
    C -- Có Nhạc Nền / Beat --> E[Tầng 2: VocalSeparator Tách Giọng AI]
    E -- Tách Thành Công --> F[Lưu audio/ + vocal_separated: true]
    E -- Lỗi Tách Giọng --> G[Tầng 3: Chuyển sang quarantine/]
```

### ⚙️ Dual-Engine trong VocalSeparator:
1. **Engine 1 (Demucs AI - Meta Research):** Dùng mô hình Deep Learning `htdemucs` bóc tách riêng biệt track Vocals & Accompaniment.
2. **Engine 2 (Spectral Vocal Cleaner - Librosa + NoiseReduce):** Phân tách Harmonic-Percussive và Spectral Gating. Xử lý cực nhanh trong **1-2 giây**, chiếm **0 MB** ổ đĩa.

---

## 8. ĐÓNG GÓI DOCKER & CHẠY TRÊN MÁY TÍNH KHÁC

Docker giúp bạn mang toàn bộ dự án sang máy tính khác (Windows, macOS, Linux Server) chạy ngay lập tức mà **không cần cài đặt lại môi trường**.

### 📦 Cách 8.1: Đóng gói thành 1 file nén `.tar` (Dùng USB / Google Drive)

> 🔵 **[Chạy trên Máy A - PowerShell tại `C:\HocC\SaydiTool`]**:

```powershell
# Xuất toàn bộ image thành 1 file duy nhất:
docker save -o audio-crawler.tar audio-crawler:latest
```

> 🔵 **[Chạy trên Máy B (Máy tính khác) - PowerShell]**:

```powershell
# 1. Nạp image từ file nén:
docker load -i audio-crawler.tar

# 2. Chạy cào ngay lập tức:
docker run --rm -v ${PWD}/Week2:/app/Week2 audio-crawler --platform facebook --keyword "học tiếng Việt"
```

---

### 🌐 Cách 8.2: Đẩy lên Docker Hub (Chạy từ bất kỳ đâu qua mạng)

> 🔵 **[Chạy trên: PowerShell tại `C:\HocC\SaydiTool`]**:

```powershell
# 1. Đăng nhập Docker Hub:
docker login

# 2. Gắn tag tên tài khoản và đẩy lên:
docker tag audio-crawler <ten_tai_khoan>/audio-crawler:latest
docker push <ten_tai_khoan>/audio-crawler:latest
```

> 🔵 **[Chạy trên: Máy tính khác bất kỳ]**:

```powershell
# Chỉ cần 1 lệnh duy nhất, Docker tự tải về và chạy:
docker run --rm -v ${PWD}/Week2:/app/Week2 <ten_tai_khoan>/audio-crawler:latest --platform tiktok --keyword "urls.txt"
```

---

## 9. ĐẨY LÊN GITHUB & CÀO CLOUD MIỄN PHÍ BẰNG GITHUB ACTIONS

### ⚠️ Lưu ý quan trọng về Lưu trữ Audio & GitHub:
- **GitHub Repo** chỉ dùng để lưu **Mã nguồn (Code)**, cấu hình và danh sách link `urls.txt`.
- Không đẩy trực tiếp 500 giờ file `.wav` (30 - 50 GB) vào Git commits vì GitHub giới hạn repo dưới 2 GB.

---

### 🚀 9.1. Đẩy Mã Nguồn Lên GitHub

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**:

```powershell
# 1. Kiểm tra trạng thái thay đổi:
git status

# 2. Lưu commit:
git add .
git commit -m "feat: complete Vietnamese audio crawler pipeline with AI vocal separation"

# 3. Liên kết tới GitHub (Chỉ làm 1 lần đầu tiên):
git remote add origin https://github.com/<tai-khoan-cua-ban>/SaydiTool.git
git branch -M main

# 4. Đẩy code lên GitHub:
git push -u origin main
```

---

### ☁️ 9.2. Giải Pháp Đỉnh Cao: Cào Trên Cloud Bằng GitHub Actions (0 MB Ổ Đĩa Máy Nhà)

Dự án đã tích hợp sẵn workflow **`.github/workflows/cloud_crawler.yml`**. Bạn có thể cào hàng trăm giờ audio trực tiếp trên máy chủ đám mây của GitHub mà **không tốn 1 byte ổ cứng hay mạng máy tính**:

#### Bước A: Thiết lập kết nối Google Drive vào GitHub Secret (Làm 1 lần)

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**:

```powershell
# Lấy toàn bộ nội dung file cấu hình Rclone:
Get-Content ~\.config\rclone\rclone.conf
```

> 🌐 **[Thực hiện trên Trình duyệt Web]**:
1. Mở trang Repo GitHub của bạn -> bấm tab **Settings**.
2. Chọn **Secrets and variables** -> bấm **Actions** -> bấm nút **New repository secret**.
3. Đặt tên Secret: **`RCLONE_CONFIG`**, dán toàn bộ nội dung file `rclone.conf` vừa lấy ở trên vào -> Bấm **Add secret**.

#### Bước B: Kích hoạt Cào trên Cloud

> 🌐 **[Thực hiện trên Trình duyệt Web]**:
1. Mở file `urls.txt` trực tiếp trên GitHub, dán danh sách link cần cào vào rồi bấm **Commit changes**.
2. Chuyển sang tab **Actions** trên GitHub -> Bấm chọn workflow **Cloud Audio Crawler to Google Drive**.
3. Bấm nút **Run workflow** -> Chọn nền tảng (`tiktok` hoặc `facebook`) -> Bấm **Run workflow**.
4. Máy chủ GitHub sẽ tự động:
   - Khởi động môi trường Linux đám mây.
   - Tự động tải video, convert WAV 16kHz mono, chạy tách giọng AI.
   - Dùng Rclone **đẩy thẳng toàn bộ file Audio sang Google Drive của bạn**.
   - Máy tính cá nhân của bạn hoàn toàn không cần bật hay tốn dung lượng!

---

## 10. ĐỒNG BỘ DỮ LIỆU SANG GOOGLE DRIVE VỚI RCLONE

### 📥 10.1. Cài đặt Rclone

> 🛡️ **[Chạy trên: PowerShell Administrator]**:

```powershell
winget install Rclone.Rclone
```

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**:

```powershell
# Cấu hình kết nối Google Drive:
rclone config
# 1. Nhập 'n' (New remote) -> Đặt tên: gdrive
# 2. Chọn loại lưu trữ: 'drive' (Google Drive)
# 3. Để trống Client ID & Secret -> Trình duyệt tự mở để bạn đăng nhập Google Drive -> Nhấn Allow
```

### ☁️ 10.2. Lệnh Đồng bộ dữ liệu

> 🔵 **[Chạy trên: PowerShell tại thư mục dự án `C:\HocC\SaydiTool`]**:

```powershell
# Xem danh sách thư mục trên Google Drive:
rclone lsd gdrive:

# Copy toàn bộ thư mục Week2 lên Google Drive folder 'ASR_Dataset/Week2':
rclone copy C:\HocC\SaydiTool\Week2 gdrive:ASR_Dataset/Week2 --progress

# Đồng bộ 2 chiều (Sync):
rclone sync C:\HocC\SaydiTool\Week2 gdrive:ASR_Dataset/Week2 --progress
```

---

## 11. BẢNG TRA CỨU TOÀN BỘ CÂU LỆNH (CHEATSHEET)

### 🐍 Lệnh Python & Crawler (Chạy tại `PS C:\HocC\SaydiTool>`):
| Mục đích | Câu lệnh PowerShell |
|---|---|
| Kích hoạt môi trường | `.\.venv\Scripts\Activate.ps1` |
| Chạy toàn bộ Unit Tests | `pytest -o pythonpath=. -v` |
| Cào TikTok qua file link | `python main.py --platform tiktok --keyword "urls.txt" --cookies cookies_tiktok.txt --workers 4` |
| Cào Facebook qua từ khóa | `python main.py --platform facebook --keyword "tin tức thời sự" --workers 4` |
| Cào toàn bộ 1 kênh TikTok | `python main.py --platform tiktok --keyword "https://www.tiktok.com/@vtv24news" --cookies cookies_tiktok.txt` |
| Thử lại các URL bị lỗi | `python retry_failed.py --platform tiktok` |
| Bỏ qua bộ lọc nhạc | `python main.py --platform tiktok --keyword "urls.txt" --skip-music-filter` |

### 🐳 Lệnh Docker (Chạy tại `PS C:\HocC\SaydiTool>`):
| Mục đích | Câu lệnh PowerShell |
|---|---|
| Build lại image | `docker build -t audio-crawler .` |
| Chạy container cào TikTok | `docker run --rm -v ${PWD}/Week2:/app/Week2 audio-crawler --platform tiktok --keyword "urls.txt"` |
| Khởi động chạy ngầm | `docker compose up -d` |
| Xem log thời gian thực | `docker compose logs -f` |
| Xuất image ra file nén | `docker save -o audio-crawler.tar audio-crawler:latest` |
| Nạp image từ file nén | `docker load -i audio-crawler.tar` |
| Dọn dẹp cache Docker | `docker system prune -af` |

### 🐙 Lệnh Git (Chạy tại `PS C:\HocC\SaydiTool>`):
| Mục đích | Câu lệnh PowerShell |
|---|---|
| Xem trạng thái thay đổi | `git status` |
| Lưu commit mới | `git add . ; git commit -m "noi dung commit"` |
| Xem lịch sử commit | `git log --oneline -n 5` |
| Đẩy code lên GitHub | `git push origin main` |

---

## 12. CẨM NANG XỬ LÝ SỰ CỐ & DEBUG LỖI (TROUBLESHOOTING)

### ❌ Lỗi 1: `ModuleNotFoundError: No module named 'yt_dlp'`
- **Môi trường bị:** PowerShell khi chạy `python main.py`.
- **Nguyên nhân:** Chưa kích hoạt môi trường ảo `.venv`.
- **Cách sửa:** Gõ `.\.venv\Scripts\Activate.ps1` trước khi chạy lệnh, hoặc chạy trực tiếp bằng `.\.venv\Scripts\python main.py ...`.

### ❌ Lỗi 2: `[Errno 21] Is a directory: 'cookies_tiktok.txt'`
- **Môi trường bị:** Docker Run trên PowerShell.
- **Nguyên nhân:** Đang đứng ở thư mục `C:\Users\Cuong>` thay vì `C:\HocC\SaydiTool>`, khiến Docker tạo ra một thư mục rỗng.
- **Cách sửa:** Gõ `cd C:\HocC\SaydiTool` trước khi chạy lệnh Docker.

### ❌ Lỗi 3: `[Errno 30] Read-only file system: 'cookies_tiktok.txt'`
- **Môi trường bị:** Docker Run khi mount `:ro`.
- **Nguyên nhân:** yt-dlp cố ghi cập nhật session vào file chỉ đọc.
- **Đã khắc phục:** Hệ thống tự động tạo bản sao ghi được trong `/tmp` để cập nhật session an toàn.

### ❌ Lỗi 4: `TypeError: '>' not supported between instances of 'float' and 'str'`
- **Nguyên nhân:** `YTDLP_RATE_LIMIT` được đặt dạng chuỗi `"500K"`.
- **Đã khắc phục:** Đã chuyển thành số nguyên byte `500 * 1024` trong `config.py`.

### ❌ Lỗi 5: `Docker 500 Internal Server Error / EOF`
- **Môi trường bị:** Docker Desktop.
- **Nguyên nhân:** Ổ C gần hết dung lượng hoặc tiến trình Docker Desktop bị treo.
- **Cách sửa:** 
  1. Click chuột phải biểu tượng Docker ở Taskbar -> chọn **Restart Docker Desktop**.
  2. Hoặc chạy trực tiếp bằng Python `.venv` (`.\.venv\Scripts\python main.py ...`) không cần Docker.

### ❌ Lỗi 6: `[Errno 28] No space left on device`
- **Nguyên nhân:** Ổ C còn dưới 5 GB dung lượng.
- **Cách sửa:**
  1. Chạy `pip cache purge` để giải phóng bộ nhớ đệm.
  2. Hệ thống đã tích hợp **Spectral Vocal Cleaner** nhẹ chỉ tốn 0 MB ổ đĩa thay vì tải 4 GB PyTorch CUDA.

### ❌ Lỗi 7: `TikTok search returns 0 URLs`
- **Nguyên nhân:** Trang tìm kiếm web của TikTok là ứng dụng JavaScript SPA chặn việc cào HTML tĩnh bằng từ khóa.
- **Cách giải quyết tối ưu:** Dán link trực tiếp vào file **`urls.txt`** hoặc truyền link kênh TikTok (VD: `https://www.tiktok.com/@vtv24news`).

---
*Tài liệu được bảo trì và tự động cập nhật bởi Antigravity AI Assistant.*
