"""
utils/rate_limiter.py — Điều tiết tốc độ request để tránh rate-limit.
Sử dụng random jitter và exponential backoff.
"""

import time
import random
import threading
from utils.logger import get_logger
from config import (
    RATE_LIMIT_MIN_SEC,
    RATE_LIMIT_MAX_SEC,
    BACKOFF_BASE_SEC,
    BACKOFF_MAX_SEC,
    MAX_RETRIES,
)

logger = get_logger("rate_limiter")


class RateLimiter:
    """
    Thread-safe rate limiter với jitter và exponential backoff.
    Mỗi thread gọi wait() trước khi thực hiện request.
    """

    def __init__(
        self,
        min_sec: float = RATE_LIMIT_MIN_SEC,
        max_sec: float = RATE_LIMIT_MAX_SEC,
    ) -> None:
        self._min = min_sec
        self._max = max_sec
        self._lock = threading.Lock()
        self._last_request_time: float = 0.0

    def wait(self) -> None:
        """Sleep đủ thời gian để đạt rate limit, nhưng KHÔNG giữ lock khi ngủ.
        Mỗi thread tính toán slot của mình và sleep độc lập — không block nhau."""
        delay = random.uniform(self._min, self._max)
        sleep_time = 0.0
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < delay:
                sleep_time = delay - elapsed
            # Đặt trước thời điểm request tiếp theo ngay trong lock
            self._last_request_time = time.monotonic() + sleep_time
        # Sleep NGOÀI lock: các thread khác có thể check lock của họ song song
        if sleep_time > 0:
            logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

    @staticmethod
    def backoff(attempt: int) -> None:
        """
        Exponential backoff sau lần thất bại thứ `attempt` (0-indexed).
        Formula: min(base * 2^attempt + jitter, max)
        """
        delay = min(
            BACKOFF_BASE_SEC * (2 ** attempt) + random.uniform(0, 3),
            BACKOFF_MAX_SEC,
        )
        logger.warning(f"Backoff attempt {attempt + 1}/{MAX_RETRIES}: sleeping {delay:.1f}s")
        time.sleep(delay)
