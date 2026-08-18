"""
utils/proxy_manager.py — Quản lý proxy và User-Agent rotation.
Khi không có proxy list, trả về None (dùng IP thực + delay thay thế).
"""

import random
import threading
from pathlib import Path
from utils.logger import get_logger
from config import PROXY_LIST_FILE, USER_AGENTS

logger = get_logger("proxy_manager")


class ProxyManager:
    """
    Quản lý danh sách proxy với round-robin và blacklist.
    Nếu không có proxy list, vẫn cung cấp User-Agent rotation.
    """

    def __init__(self, proxy_file: Path | None = PROXY_LIST_FILE) -> None:
        self._proxies: list[str] = []
        self._blacklist: set[str] = set()
        self._index: int = 0
        self._lock = threading.Lock()
        self._ua_index: int = 0

        if proxy_file and proxy_file.exists():
            lines = proxy_file.read_text(encoding="utf-8").splitlines()
            self._proxies = [
                line.strip() for line in lines
                if line.strip() and not line.startswith("#")
            ]
            logger.info(f"Loaded {len(self._proxies)} proxies from {proxy_file}")
        else:
            logger.info("No proxy file — running without proxy (delay-based anti-block only)")

    def get_proxy(self) -> dict | None:
        """
        Trả về proxy dict cho yt-dlp, hoặc None nếu không có proxy.
        Format: {"http": "http://ip:port", "https": "http://ip:port"}
        """
        with self._lock:
            available = [p for p in self._proxies if p not in self._blacklist]
            if not available:
                return None

            proxy = available[self._index % len(available)]
            self._index += 1

            if not proxy.startswith("http"):
                proxy = f"http://{proxy}"

            return {"http": proxy, "https": proxy}

    def blacklist_proxy(self, proxy: str) -> None:
        """Đánh dấu proxy bị block để không dùng lại."""
        with self._lock:
            self._blacklist.add(proxy)
            logger.warning(f"Blacklisted proxy: {proxy}")

    def get_user_agent(self) -> str:
        """Round-robin User-Agent."""
        with self._lock:
            ua = USER_AGENTS[self._ua_index % len(USER_AGENTS)]
            self._ua_index += 1
            return ua

    def get_ydl_headers(self) -> dict:
        """Trả về http_headers dict để inject vào yt-dlp options."""
        return {
            "User-Agent": self.get_user_agent(),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.google.com/",
        }
