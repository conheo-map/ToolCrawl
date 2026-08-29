"""
utils/cookie_manager.py — Quản lý và xoay vòng nhiều file Cookies (Cookie Rotation).
Hỗ trợ nạp đơn file hoặc toàn bộ thư mục cookies/ (Round-Robin).
"""

import threading
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("cookie_manager")


class CookieManager:
    """
    Quản lý danh sách file cookie và phân bổ xoay vòng (thread-safe).
    """

    def __init__(self, cookie_input: Path | str | None = None, platform: str = "tiktok") -> None:
        self._cookies: list[Path] = []
        self._bad_cookies: set[Path] = set()
        self._index: int = 0
        self._lock = threading.Lock()
        self._platform = platform

        self._load(cookie_input)

    def _load(self, cookie_input: Path | str | None) -> None:
        """Nạp danh sách cookie từ file, thư mục hoặc default folder."""
        paths_to_check = []

        if cookie_input:
            p = Path(cookie_input)
            if p.is_file():
                self._cookies.append(p)
                logger.info(f"Loaded single cookie file: {p.name}")
                return
            elif p.is_dir():
                paths_to_check.append(p)
        else:
            # Default paths to check
            default_dir = Path("cookies")
            if default_dir.is_dir():
                paths_to_check.append(default_dir)

        for folder in paths_to_check:
            txt_files = list(folder.glob("*.txt"))
            for f in txt_files:
                # Nếu có tiền tố platform (ví dụ tiktok_01.txt, fb_01.txt) hoặc file chung
                if self._platform in f.stem.lower() or "cookie" in f.stem.lower() or len(txt_files) == 1:
                    self._cookies.append(f)
                else:
                    self._cookies.append(f)

        # Deduplicate
        self._cookies = sorted(list(set(self._cookies)))

        if self._cookies:
            logger.info(f"🍪 [CookieManager] Loaded {len(self._cookies)} rotating cookie file(s): {[c.name for c in self._cookies]}")
        else:
            logger.info("No cookie files found — running in public / anonymous mode")

    def get_cookie(self) -> Path | None:
        """Trả về 1 cookie file theo cơ chế xoay vòng Round-Robin."""
        with self._lock:
            available = [c for c in self._cookies if c not in self._bad_cookies and c.exists()]
            if not available:
                return None

            cookie = available[self._index % len(available)]
            self._index += 1
            return cookie

    def mark_bad(self, cookie_path: Path) -> None:
        """Đánh dấu cookie bị lỗi (hết hạn, captcha) để tạm ngưng dùng."""
        with self._lock:
            self._bad_cookies.add(cookie_path)
            logger.warning(f"⚠️ [CookieManager] Blacklisted bad/expired cookie: {cookie_path.name}")

    def reset_bad_cookies(self) -> None:
        """Xóa blacklist để thử lại."""
        with self._lock:
            self._bad_cookies.clear()
            logger.info("🔄 [CookieManager] Reset bad cookies blacklist")

    def count(self) -> int:
        with self._lock:
            return len([c for c in self._cookies if c not in self._bad_cookies])
