"""
config.py — Cấu hình trung tâm cho toàn bộ crawler pipeline.
Chỉnh sửa tại đây; không hardcode thông số ở các module khác.
"""

from pathlib import Path
import datetime
import os

# ─────────────────────────────────────────────
# Project root
# ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.resolve()

# ─────────────────────────────────────────────
# Tuần & Ngày crawl (Theo chuẩn Giờ Việt Nam GMT+7)
# ─────────────────────────────────────────────
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
CRAWL_DATE: str = datetime.datetime.now(VN_TZ).date().isoformat()

def get_current_week(dt: datetime.date | str | None = None) -> int:
    """
    Tự động tính số tuần chuẩn:
    - Week 1: trước 24/08/2026 (20/8 - 23/8)
    - Week 2: 24/08 - 30/08/2026
    - Week 3: 31/08 - 06/09/2026
    - Week 4: 07/09 - 13/09/2026
    - Cứ tiếp tục mỗi 7 ngày tăng 1 tuần.
    """
    if dt is None:
        dt = datetime.datetime.now(VN_TZ).date()
    elif isinstance(dt, str):
        dt = datetime.date.fromisoformat(dt)
    anchor_week2 = datetime.date(2026, 8, 24)
    if dt < anchor_week2:
        return 1
    return 2 + ((dt - anchor_week2).days // 7)

WEEK_NUMBER: int = get_current_week()

# ─────────────────────────────────────────────
# Thư mục output (theo spec)
# ─────────────────────────────────────────────
BASE_OUTPUT_DIR: Path = PROJECT_ROOT / f"Week{WEEK_NUMBER}" / CRAWL_DATE
AUDIO_DIR:       Path = BASE_OUTPUT_DIR / "audio"
ERRORS_DIR:      Path = PROJECT_ROOT / "errors"
QUARANTINE_DIR:  Path = BASE_OUTPUT_DIR / "quarantine"  # Default: ngày crawl hiện tại
CHECKPOINT_DIR:  Path = PROJECT_ROOT / ".checkpoints"

METADATA_FILE:   Path = BASE_OUTPUT_DIR / "metadata.json"
SUMMARY_FILE:    Path = BASE_OUTPUT_DIR / "summary.json"
SEEN_IDS_FILE:   Path = PROJECT_ROOT / ".checkpoints" / "seen_ids.json"


def get_quarantine_dir(crawl_date: str | None = None) -> Path:
    """
    [FIX 1.1] Trả về đúng thư mục quarantine theo ngày crawl GỐC của file,
    thay vì dùng ngày hôm nay (CRAWL_DATE).

    Lý do: Bug cũ ghi quarantine theo ngày runtime → khi retry/reprocess file
    cũ, quarantined_count trong summary.json bị inflated sai (vd: 24-25/08 có
    quarantined_count > items_delivered).

    Sử dụng:
        quarantine_dir = get_quarantine_dir(record.get("crawl_date") or CRAWL_DATE)
        quarantine_dir.mkdir(parents=True, exist_ok=True)
    """
    date = crawl_date or CRAWL_DATE
    week = get_current_week(date)
    return PROJECT_ROOT / f"Week{week}" / date / "quarantine"

# ─────────────────────────────────────────────
# Thông số Audio (chuẩn đầu ra)
# ─────────────────────────────────────────────
AUDIO_SAMPLE_RATE: int = 16_000
AUDIO_CHANNELS:    int = 1
AUDIO_FORMAT:      str = "wav"
AUDIO_CODEC:       str = "pcm_s16le"

MIN_DURATION_SEC: float = 5.0
MAX_DURATION_SEC: float = 7200.0   # Cho phép cào video dài tới 2 tiếng (tự động cắt thành các đoạn ASR 5s - 30s)

# ─────────────────────────────────────────────
# Parallel workers
# ─────────────────────────────────────────────
MAX_WORKERS: int = int(os.getenv("CRAWLER_WORKERS", "4"))

# ─────────────────────────────────────────────
# Rate limiting (anti-block)
# ─────────────────────────────────────────────
RATE_LIMIT_MIN_SEC: float = 1.5
RATE_LIMIT_MAX_SEC: float = 4.5
BACKOFF_BASE_SEC:   float = 10.0
BACKOFF_MAX_SEC:    float = 120.0
MAX_RETRIES:        int   = 3

# ─────────────────────────────────────────────
# yt-dlp download settings (Tối đa tốc độ đường truyền)
# ─────────────────────────────────────────────
YTDLP_RATE_LIMIT: int | None = None  # Unlimited speed
YTDLP_SOCKET_TIMEOUT: int = 30
YTDLP_RETRIES: int = 3

USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

TIKTOK_COOKIES_FILE:   Path | None = None
FACEBOOK_COOKIES_FILE: Path | None = None
PROXY_LIST_FILE: Path | None = None

# ─────────────────────────────────────────────
# Music Detection
# ─────────────────────────────────────────────
MUSIC_FILTER_ENABLED: bool = True
MUSIC_FLATNESS_THRESHOLD: float = 0.35
MUSIC_REJECT_RATIO: float = 0.60
MUSIC_ANALYSIS_SAMPLE_SEC: float = 30.0
MUSIC_QUARANTINE_INSTEAD_OF_DELETE: bool = True

# [UPGRADE 2.2] Music Probability thresholds — thay thế binary True/False
# Dùng với _check_signal_multiwindow() trả về music_prob float 0.0–1.0
MUSIC_PROB_REJECT:   float = 0.70   # > 70% → QUARANTINE (hard reject)
MUSIC_PROB_SEPARATE: float = 0.30   # 30–70% → VocalSeparator
MUSIC_PROB_AUGMENT:  float = 0.15   # 15–30% → Giữ lại, tag 'augment_bgm'
# < 15%                             → Clean path, no action

# [UPGRADE 2.2] HPSS signal thresholds — hạ xuống để bắt BGM nhẹ hơn
HPSS_HARM_RATIO_THRESHOLD: float = 0.45   # Từ 0.60 → 0.45
HPSS_CONTRAST_THRESHOLD:   float = 20.0   # Từ 22.0 → 20.0
HPSS_FLATNESS_THRESHOLD:   float = 0.015  # Giữ nguyên

# [FIX 1.3] SNR Hard-Reject gate — nâng từ 8.0 dB → 10.0 dB
# Đóng khoảng gap 4dB giữa min_snr (12dB) và gate cũ (8dB)
MUSIC_SNR_HARD_REJECT_DB: float = 10.0

# ─────────────────────────────────────────────
# Synthetic Speech Detection (SSD)            [MỚI — Điểm Nghẽn #7]
# ─────────────────────────────────────────────
SSD_ENABLED: bool = True
SSD_PROB_REJECT:  float = 0.70   # > 70% → QUARANTINE (tag: tts_generated)
SSD_PROB_FLAG:    float = 0.30   # 30–70% → FLAG (tag: possibly_synthetic)
# < 30%                          → PASS (real human speech)

# Ngưỡng feature heuristic Tầng 1 (không cần GPU)
SSD_F0_JITTER_THRESHOLD:    float = 0.008   # < 0.008 → nghi ngờ TTS
SSD_MFCC_VAR_THRESHOLD:     float = 15.0    # < 15.0  → nghi ngờ TTS
SSD_SPECTRAL_FLUX_THRESHOLD: float = 0.002  # < 0.002 → vocoder smoothing

# ─────────────────────────────────────────────
# Smart Audio Slicer & Acoustic Padding Guard
# ─────────────────────────────────────────────
AUDIO_SLICER_ENABLED: bool = True
ASR_TARGET_MODEL: str = os.getenv("ASR_TARGET_MODEL", "balanced")  # "whisper" (30s) | "conformer" (15s) | "balanced" (20s)
MAX_ASR_SEGMENT_SEC: float = 30.0 if ASR_TARGET_MODEL == "whisper" else (15.0 if ASR_TARGET_MODEL == "conformer" else 20.0)
MIN_ASR_SEGMENT_SEC: float = 3.0
SILENCE_THRESHOLD_DB: float = -32.0
MIN_SILENCE_DURATION_SEC: float = 0.35
PRE_SPEECH_PADDING_SEC: float = 0.20   # Dem khoang lang 0.20s o dau cau chong nuot phu am
POST_SPEECH_PADDING_SEC: float = 0.25  # Dem khoang lang 0.25s o cuoi cau chong mat mut am
TRUE_PEAK_MAX_DBFS: float = -1.0       # Nguong tran Headroom chong clipping

# [UPGRADE 2.3] Silero VAD constants cho VadSlicer
SILERO_VAD_THRESHOLD:  float = 0.50   # Nguong speech/non-speech (0.0-1.0)
SILERO_MIN_SPEECH_MS:  int   = 250    # Doan noi toi thieu (ms) de tinh la speech
SILERO_MIN_SILENCE_MS: int   = 100    # Khoang lang toi thieu (ms) giua 2 doan noi


# ─────────────────────────────────────────────
# Bộ từ khóa cào tự động 24/7 (Auto Keywords)
# ─────────────────────────────────────────────
AUTO_CRAWL_KEYWORDS: list[str] = [
    "tin tức thời sự",
    "học tiếng Việt",
    "podcast tiếng Việt",
    "sách nói hay",
    "chia sẻ kiến thức",
    "lịch sử Việt Nam",
    "review ẩm thực Việt Nam",
    "kể chuyện đêm khuya",
]


# ─────────────────────────────────────────────
# Cloud Speech AI API (Groq / Gemini / OpenAI)
# ─────────────────────────────────────────────
CLOUD_SPEECH_ENABLED: bool = True
CLOUD_SPEECH_PROVIDER: str = os.getenv("CLOUD_SPEECH_PROVIDER", "auto")  # "groq" | "gemini" | "openai" | "local" | "auto"
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ─────────────────────────────────────────────
# Telegram Bot Configuration
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USERS: list[int] = [
    int(uid.strip()) for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if uid.strip().isdigit()
]


def make_batch_id(platform: str, batch_num: int = 1) -> str:
    """Tạo crawl_batch ID theo format spec: tt_20260817_01"""
    prefix = "tt" if platform == "tiktok" else "fb"
    date_compact = CRAWL_DATE.replace("-", "")
    return f"{prefix}_{date_compact}_{batch_num:02d}"

