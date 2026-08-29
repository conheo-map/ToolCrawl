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
WEEK_NUMBER: int = 3
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
CRAWL_DATE: str = datetime.datetime.now(VN_TZ).date().isoformat()

# ─────────────────────────────────────────────
# Thư mục output (theo spec)
# ─────────────────────────────────────────────
BASE_OUTPUT_DIR: Path = PROJECT_ROOT / f"Week{WEEK_NUMBER}" / CRAWL_DATE
AUDIO_DIR:       Path = BASE_OUTPUT_DIR / "audio"
ERRORS_DIR:      Path = PROJECT_ROOT / "errors"
QUARANTINE_DIR:  Path = BASE_OUTPUT_DIR / "quarantine"
CHECKPOINT_DIR:  Path = PROJECT_ROOT / ".checkpoints"

METADATA_FILE:   Path = BASE_OUTPUT_DIR / "metadata.json"
SUMMARY_FILE:    Path = BASE_OUTPUT_DIR / "summary.json"
SEEN_IDS_FILE:   Path = PROJECT_ROOT / ".checkpoints" / "seen_ids.json"

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

# ─────────────────────────────────────────────
# Smart Audio Slicer (ASR Standard 5s - 30s)
# ─────────────────────────────────────────────
AUDIO_SLICER_ENABLED: bool = True
MAX_ASR_SEGMENT_SEC: float = 30.0
MIN_ASR_SEGMENT_SEC: float = 5.0
SILENCE_THRESHOLD_DB: float = -32.0
MIN_SILENCE_DURATION_SEC: float = 0.35


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

