"""
crawlers/base.py — BaseCrawler: yt-dlp wrapper với retry, fallback, và audio download.
"""

import json
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

_error_lock = threading.Lock()

import yt_dlp

from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.proxy_manager import ProxyManager
from utils.cookie_manager import CookieManager
from processors.audio_converter import convert_to_wav, verify_audio
from config import (
    AUDIO_DIR,
    ERRORS_DIR,
    MAX_RETRIES,
    MIN_DURATION_SEC,
    MAX_DURATION_SEC,
    YTDLP_RATE_LIMIT,
    YTDLP_SOCKET_TIMEOUT,
    YTDLP_RETRIES,
    CRAWL_DATE,
)

logger = get_logger("base_crawler")
VN_TZ = timezone(timedelta(hours=7))


class DownloadError(Exception):
    """Raised khi download thất bại sau khi retry."""


class BaseCrawler:
    """
    Base class cho TikTokCrawler và FacebookCrawler.
    Xử lý: download, convert, verify, retry logic và xoay vòng Cookie.
    """

    PLATFORM = "base"
    ID_PREFIX = "xx"

    def __init__(
        self,
        cookies_file: Path | None = None,
        rate_limiter: RateLimiter | None = None,
        proxy_manager: ProxyManager | None = None,
        cookie_manager: CookieManager | None = None,
    ) -> None:
        self._cookie_manager = cookie_manager or CookieManager(cookie_input=cookies_file, platform=self.PLATFORM)
        self._rate = rate_limiter or RateLimiter()
        self._proxy = proxy_manager or ProxyManager()
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        ERRORS_DIR.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def download_audio(self, url: str, item_id: str) -> dict:
        """
        Download audio từ URL và convert về WAV 16kHz mono.
        Trả về dict chứa thông tin cần thiết cho metadata.
        Raise DownloadError sau MAX_RETRIES lần thất bại.
        """
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                self._rate.wait()
                result = self._try_download(url, item_id)
                return result
            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                logger.warning(f"Download attempt {attempt + 1}/{MAX_RETRIES} failed for {item_id}: {err_str}")

                # Nhận diện lỗi không thể cứu (Video bị xóa, private, câm, quá ngắn/dài) -> Bỏ qua ngay lập tức, không retry
                unrecoverable = any(p in err_str.lower() for p in [
                    "no audio stream",
                    "video unavailable",
                    "this video is private",
                    "private video",
                    "post has been removed",
                    "http error 404",
                    "audio too short",
                    "audio too long"
                ])
                if unrecoverable:
                    logger.warning(f"Bỏ qua {item_id} ngay vòng {attempt + 1} (Lỗi không thể phục hồi): {err_str}")
                    self._log_error(url, item_id, err_str)
                    raise DownloadError(f"UNRECOVERABLE: {err_str}") from exc

                if "429" in err_str or "Too Many Requests" in err_str:
                    current = self._proxy.get_proxy()
                    if current:
                        self._proxy.blacklist_proxy(current["http"])

                if attempt < MAX_RETRIES - 1:
                    RateLimiter.backoff(attempt)

        # Lưu vào errors list để retry sau
        self._log_error(url, item_id, str(last_error))
        raise DownloadError(
            f"Failed after {MAX_RETRIES} attempts: {last_error}"
        ) from last_error

    def extract_info(self, url: str) -> dict:
        """Lấy metadata của video mà không download."""
        opts = self._build_ydl_opts(download=False)
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False) or {}

    # ─────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────

    def _try_download(self, url: str, item_id: str) -> dict:
        """Thực hiện 1 lần download."""
        wav_output = AUDIO_DIR / f"{item_id}.wav"

        if wav_output.exists():
            # Đã download rồi (resume) — lấy metadata info_dict mà không download lại audio
            logger.debug(f"Already downloaded: {item_id}.wav — extracting metadata")
            info = verify_audio(wav_output)
            try:
                info_dict = self.extract_info(url)
            except Exception:
                info_dict = {}
            return {
                "audio_path": wav_output,
                "duration_seconds": info["duration_seconds"],
                "info_dict": info_dict,
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            opts = self._build_ydl_opts(download=True, output_dir=tmp_path)

            with yt_dlp.YoutubeDL(opts) as ydl:
                info_dict = ydl.extract_info(url, download=True) or {}

            # Tìm file vừa download
            downloaded = list(tmp_path.glob("*"))
            if not downloaded:
                raise RuntimeError(f"yt-dlp produced no output files for {url}")

            # Lấy file audio (yt-dlp có thể ra nhiều file, lấy file lớn nhất)
            src = max(downloaded, key=lambda p: p.stat().st_size)

            # Convert to WAV
            duration = convert_to_wav(src, wav_output)

        # Kiểm tra duration
        if duration < MIN_DURATION_SEC:
            wav_output.unlink(missing_ok=True)
            raise ValueError(
                f"Audio too short: {duration:.1f}s < {MIN_DURATION_SEC}s"
            )
        if duration > MAX_DURATION_SEC:
            wav_output.unlink(missing_ok=True)
            raise ValueError(
                f"Audio too long: {duration:.1f}s > {MAX_DURATION_SEC}s"
            )

        logger.info(f"Downloaded & converted: {item_id}.wav ({duration:.1f}s)")
        return {
            "audio_path": wav_output,
            "duration_seconds": duration,
            "info_dict": info_dict,
        }

    def _build_ydl_opts(
        self, download: bool = True, output_dir: Path | None = None
    ) -> dict:
        """Xây dựng yt-dlp options dict."""
        proxy_dict = self._proxy.get_proxy()
        headers = self._proxy.get_ydl_headers()

        opts: dict = {
            "quiet": True,
            "no_warnings": False,
            "http_headers": headers,
            "socket_timeout": YTDLP_SOCKET_TIMEOUT,
            "retries": YTDLP_RETRIES,
            "fragment_retries": YTDLP_RETRIES,
            "ignoreerrors": False,
        }

        if proxy_dict:
            opts["proxy"] = proxy_dict.get("http", "")

        cookie_file = self._cookie_manager.get_cookie() if self._cookie_manager else None
        if cookie_file and cookie_file.exists():
            opts["cookiefile"] = str(cookie_file)

        if download and output_dir:
            opts["outtmpl"] = str(output_dir / "%(id)s.%(ext)s")
            opts["format"] = "bestaudio/best"
            if YTDLP_RATE_LIMIT is not None:
                opts["ratelimit"] = int(YTDLP_RATE_LIMIT)
            opts["keepvideo"] = False
            opts["extractaudio"] = False

        return opts

    def _log_error(self, url: str, item_id: str, error: str) -> None:
        """Ghi lỗi vào errors/failed_<date>.jsonl để retry sau."""
        error_file = ERRORS_DIR / f"failed_{CRAWL_DATE}.jsonl"
        record = {
            "url": url,
            "item_id": item_id,
            "platform": self.PLATFORM,
            "error": error,
            "failed_at": datetime.now(VN_TZ).isoformat(timespec="seconds"),
        }
        with _error_lock:
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.debug(f"Logged error for {item_id} -> {error_file.name}")
