# Tài Liệu Kỹ Thuật — Facebook & TikTok Audio Crawler

## 1. Tổng quan hệ thống

Pipeline crawl audio tiếng Việt từ Facebook Reels và TikTok, phục vụ huấn luyện mô hình ASR.

### Kiến trúc

```
main.py (CLI + orchestrator)
  ├── crawlers/          → Search URLs + Download audio
  │   ├── base.py        → yt-dlp wrapper, retry, temp download
  │   ├── tiktok.py      → TikTok search + metadata
  │   └── facebook.py    → Facebook search + metadata
  ├── processors/        → Audio processing
  │   ├── audio_converter.py → FFmpeg WAV 16kHz mono + ffprobe verify
  │   └── music_detector.py  → Lọc nhạc nền (metadata + librosa)
  ├── storage/           → Persistence layer
  │   ├── dedup.py       → Lọc trùng item_id
  │   ├── metadata_writer.py → Thread-safe JSON writer
  │   └── state_manager.py   → Checkpoint/resume
  └── utils/             → Cross-cutting
      ├── logger.py      → Structured logging
      ├── rate_limiter.py → Jitter + exponential backoff
      └── proxy_manager.py → Proxy rotation + User-Agent spoofing
```

### Flow xử lý 1 video

```
Keyword → Search URLs → [cho mỗi URL, song song]
  → Check checkpoint (skip nếu đã done)
  → Check dedup (skip nếu đã có item_id)
  → yt-dlp download (bestaudio) → temp file
  → FFmpeg convert → WAV 16kHz mono
  → ffprobe verify spec
  → Check duration (5s – 600s)
  → Music detection (metadata heuristic → librosa signal)
  → Ghi metadata.json (thread-safe)
  → Cập nhật checkpoint + dedup store
```

---

## 2. Giải pháp cho các vấn đề kỹ thuật

### 2.1. Trùng lặp ID

**Vấn đề:** Crawl nhiều keywords sẽ trả về cùng video.

**Giải pháp:**
- `DedupStore` duy trì set `item_id` trong RAM + persist vào `.checkpoints/seen_ids.json`
- Thread-safe với `threading.Lock`
- Kiểm tra trước khi download → tiết kiệm bandwidth
- Persist qua session: load lại khi restart

### 2.2. Cơ chế Fallback / Checkpoint

**Vấn đề:** Download bị ngắt giữa chừng do mạng, rate limit, hoặc Ctrl+C.

**Giải pháp:**
- `StateManager` lưu trạng thái từng URL (`done` / `failed`) vào checkpoint file theo ngày
- Khi restart: load checkpoint → skip URLs đã `done`
- URLs `failed` được lưu kèm error message → dùng `retry_failed.py` để retry
- Graceful shutdown: bắt SIGINT → set flag `_shutdown` → workers kết thúc tự nhiên
- Mỗi record `metadata.json` được flush ngay sau khi ghi (atomic write via temp file + rename)

### 2.3. Chuẩn định dạng audio

**Vấn đề:** Nguồn video có format audio khác nhau (AAC, MP3, OPUS, v.v.).

**Giải pháp:**
- **FFmpeg** convert 100% output: `-ar 16000 -ac 1 -acodec pcm_s16le -f wav`
- **ffprobe** verify sau convert: kiểm tra sample_rate, channels, codec
- Nếu verify thất bại → raise error → file bị xóa và ghi lỗi

### 2.4. Lọc nhạc nền

**Vấn đề:** Nhiều video TikTok/FB dính nhạc nền.

**Giải pháp 2 tầng:**

**Tầng 1 — Metadata heuristic (0ms, zero CPU):**
- TikTok: kiểm tra `music_is_original` từ yt-dlp info_dict
- Nếu `music_is_original=False` và track name không phải "original sound" → reject
- Nếu `music_is_original=True` → pass (skip signal analysis)

**Tầng 2 — Signal analysis (chỉ khi metadata không rõ):**
- Dùng `librosa.feature.spectral_flatness` trên 30 giây đầu
- Spectral flatness < 0.25 → có tín hiệu nhạc (năng lượng tập trung ở tần số nhất định)
- Spectral flatness > 0.25 → speech (năng lượng phân bố đều)
- Audio bị reject được move vào `quarantine/` (không xóa, để review thủ công)

**Cấu hình:**
- `MUSIC_FILTER_ENABLED`: bật/tắt
- `MUSIC_FLATNESS_THRESHOLD`: ngưỡng flatness (default 0.25)
- `MUSIC_QUARANTINE_INSTEAD_OF_DELETE`: quarantine thay vì xóa

### 2.5. Xử lý đồng thời & Rate Limit

**Vấn đề:** Chạy song song nhưng phải tránh rate limit và đảm bảo data integrity.

**Giải pháp:**

**Concurrency:**
- `ThreadPoolExecutor` với MAX_WORKERS (default 4) workers
- Mỗi worker xử lý lỗi độc lập — 1 video lỗi không dừng toàn bộ
- `threading.Lock` bảo vệ: DedupStore, MetadataWriter, StateManager, RateLimiter

**Rate limiting:**
- `RateLimiter`: random delay [1.5s, 4.5s] giữa các request
- Exponential backoff khi lỗi: `min(10 * 2^attempt + jitter, 120s)`
- yt-dlp rate limit: 500KB/s download speed

**Data safety:**
- Metadata ghi atomic: write temp file → rename (tránh corrupt khi crash)
- Checkpoint update sau mỗi URL (không mất progress)

### 2.6. Khôi phục & Chống chặn IP

**Vấn đề:** Facebook/TikTok chặn IP hoặc checkpoint tài khoản.

**Giải pháp (không có proxy):**
- **User-Agent rotation**: 6 UA khác nhau, round-robin
- **Accept-Language**: set `vi-VN` để giả lập user Việt Nam
- **Referer spoofing**: set Google referer
- **Random jitter**: delay ngẫu nhiên giữa requests
- **yt-dlp rate limit**: giới hạn bandwidth 500KB/s
- **Cookie support**: hỗ trợ Netscape cookie file khi có
  - Export bằng browser extension (ví dụ: "Get cookies.txt LOCALLY")
  - Truyền qua CLI: `--cookies cookies_tiktok.txt`

**Nếu có proxy sau này:**
- Đặt file `proxies.txt` (1 proxy/dòng, format `ip:port` hoặc `http://ip:port`)
- `ProxyManager` tự động round-robin + blacklist proxy bị chặn

---

## 3. Quy trình Post-processing Audio

### 3.1. Pipeline tự động (trong crawler)

```
1. Download raw audio (bất kỳ format nào)
2. FFmpeg convert → WAV 16kHz mono PCM S16LE
3. ffprobe verify (sample_rate, channels, codec)
4. Duration check (5s ≤ duration ≤ 600s)
5. Music detection (metadata + signal analysis)
6. Ghi metadata JSON + cập nhật summary
```

### 3.2. Post-processing thủ công (sau crawl)

**Bước 1: Review quarantine**
```bash
# Liệt kê audio nghi có nhạc
ls Week2/2026-08-18/quarantine/

# Nghe thử và quyết định keep/delete
# Nếu clean: move về audio/
# Nếu thực sự có nhạc: xóa
```

**Bước 2: Retry failed**
```bash
python retry_failed.py --platform tiktok --date 2026-08-18 --workers 2
```

**Bước 3: Kiểm tra chất lượng mẫu**
```bash
# Verify ngẫu nhiên 10 file
for f in $(ls Week2/2026-08-18/audio/ | shuf -n 10); do
    ffprobe -v quiet -print_format json -show_streams "Week2/2026-08-18/audio/$f"
done
```

**Bước 4: Thống kê**
```bash
# Xem summary
cat Week2/2026-08-18/summary.json | python -m json.tool
```

---

## 4. Hướng dẫn sử dụng

### Cài đặt

```bash
# Cài dependencies
pip install -r requirements.txt

# Cài FFmpeg (Windows)
winget install FFmpeg
# Hoặc download từ https://ffmpeg.org/download.html
```

### Chạy crawl

```bash
# TikTok
python main.py --platform tiktok --keyword "review quán ăn" --workers 4

# Facebook
python main.py --platform facebook --keyword "học tiếng Việt" --workers 4

# Dry-run (chỉ search, không download)
python main.py --platform tiktok --keyword "tin tức" --dry-run

# Với cookie
python main.py --platform tiktok --keyword "du lịch" --cookies cookies_tiktok.txt

# Tuần khác
python main.py --platform tiktok --keyword "ẩm thực" --week 3
```

### Export cookie từ browser

1. Cài extension "Get cookies.txt LOCALLY" trên Chrome/Firefox
2. Đăng nhập TikTok/Facebook trên browser
3. Export cookies sang file `.txt` (Netscape format)
4. Đặt file tại thư mục project: `cookies_tiktok.txt` hoặc `cookies_facebook.txt`

---

## 5. Format dữ liệu đầu ra

### Cấu trúc thư mục
```
Week2/2026-08-18/
├── audio/
│   ├── tt_7412345678901234567.wav
│   └── fb_123456789012345.wav
├── quarantine/          (audio nghi có nhạc nền)
├── metadata.json        (JSON array of records)
└── summary.json         (daily summary)
```

### Metadata record (mỗi audio)
```json
{
  "item_id": "tt_7412345678901234567",
  "platform": "tiktok",
  "platform_video_id": "7412345678901234567",
  "video_url": "https://www.tiktok.com/@user/video/7412345678901234567",
  "title": "Review quán ăn Hà Nội",
  "description": "full caption + #hashtag",
  "posted_at": "2026-08-10T13:22:05+07:00",
  "language_raw": "vi",
  "audio_path": "audio/tt_7412345678901234567.wav",
  "duration_seconds": 187.44,
  "crawl_batch": "tt_20260818_01",
  "crawled_at": "2026-08-18T09:14:00+07:00",
  "platform_meta": {
    "music_is_original": true,
    "is_duet": false,
    "is_stitch": false,
    "has_platform_captions": true
  }
}
```

### Summary (daily)
```json
{
  "platform": "tiktok",
  "crawl_date": "2026-08-18",
  "batch_count": 1,
  "audio_spec": {
    "sample_rate": 16000,
    "channels": 1,
    "format": "wav_pcm_s16le"
  },
  "items_delivered": 742,
  "unique_item_ids": 738,
  "total_hours": 34.5,
  "error_count": 26
}
```
