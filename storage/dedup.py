"""
storage/dedup.py — Lọc trùng item_id qua nhiều session crawl.
"""

import json
import threading
from pathlib import Path
from utils.logger import get_logger
from config import SEEN_IDS_FILE, CHECKPOINT_DIR

logger = get_logger("dedup")


class DedupStore:
    """
    Thread-safe store để lọc trùng item_id.
    Persist danh sách vào file JSON để duy trì qua nhiều lần chạy.
    """

    def __init__(self, store_path: Path = SEEN_IDS_FILE) -> None:
        self._path = store_path
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        """Load danh sách seen_ids từ file (nếu có)."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._seen = set(data.get("seen_ids", []))
                logger.info(
                    f"Loaded {len(self._seen)} seen IDs from {self._path.name}"
                )
            except Exception as exc:
                logger.warning(f"Could not load dedup store: {exc} — starting fresh")
                self._seen = set()
        else:
            logger.info("No dedup store found — starting fresh")

    def is_seen(self, item_id: str) -> bool:
        """Kiểm tra item_id đã crawl chưa."""
        with self._lock:
            return item_id in self._seen

    def mark_seen(self, item_id: str) -> None:
        """Đánh dấu item_id đã xử lý xong."""
        with self._lock:
            self._seen.add(item_id)

    def save(self) -> None:
        """Ghi danh sách seen_ids xuống file (atomic write)."""
        with self._lock:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"seen_ids": sorted(self._seen)},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            tmp.replace(self._path)
            logger.debug(f"Saved {len(self._seen)} seen IDs")

    def count(self) -> int:
        """Số lượng item_id đã thấy."""
        with self._lock:
            return len(self._seen)
