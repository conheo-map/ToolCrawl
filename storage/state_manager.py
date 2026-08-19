"""
storage/state_manager.py — Checkpoint và resume cơ chế.
Lưu trạng thái từng URL để tiếp tục khi bị ngắt.
"""

import json
import threading
from pathlib import Path
from datetime import datetime, timezone
from utils.logger import get_logger
from config import CHECKPOINT_DIR, CRAWL_DATE

logger = get_logger("state_manager")


class StateManager:
    """
    Theo dõi trạng thái của từng URL trong pipeline:
    - done: đã xử lý thành công
    - failed: lỗi (lưu để retry sau)
    Persist vào checkpoint file theo ngày.
    """

    def __init__(self, platform: str, checkpoint_file: Path | None = None) -> None:
        self._platform = platform
        self._lock = threading.Lock()
        self._done: set[str] = set()
        self._failed: dict[str, str] = {}  # url -> error_message
        if checkpoint_file:
            self._path = checkpoint_file
            self._path.parent.mkdir(parents=True, exist_ok=True)
        else:
            CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
            self._path = CHECKPOINT_DIR / f"checkpoint_{platform}_{CRAWL_DATE}.json"
        self._load()

    def _load(self) -> None:
        """Load checkpoint từ file (nếu có)."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._done = set(data.get("done", []))
                self._failed = data.get("failed", {})
                logger.info(
                    f"Checkpoint loaded: {len(self._done)} done, "
                    f"{len(self._failed)} failed"
                )
            except Exception as exc:
                logger.warning(f"Could not load checkpoint: {exc}")

    def is_done(self, url: str) -> bool:
        """Kiểm tra URL đã xử lý thành công chưa."""
        with self._lock:
            return url in self._done

    def mark_done(self, url: str) -> None:
        """Đánh dấu URL đã xử lý xong."""
        with self._lock:
            self._done.add(url)
            self._failed.pop(url, None)
            self._save_unsafe()

    def add_failed(self, url: str, error: str) -> None:
        """Ghi nhận URL lỗi kèm thông báo lỗi."""
        with self._lock:
            self._failed[url] = error
            self._save_unsafe()

    def load_failed(self) -> dict[str, str]:
        """Trả về dict url -> error_message để dùng trong retry_failed.py."""
        with self._lock:
            return dict(self._failed)

    def _save_unsafe(self) -> None:
        """Ghi checkpoint xuống file (không thread-safe — gọi khi đang giữ lock)."""
        data = {
            "platform": self._platform,
            "crawl_date": CRAWL_DATE,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "done_count": len(self._done),
            "failed_count": len(self._failed),
            "done": sorted(self._done),
            "failed": self._failed,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def stats(self) -> dict:
        """Trả về số lượng done và failed."""
        with self._lock:
            return {"done": len(self._done), "failed": len(self._failed)}
