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
        """Load danh sách seen_ids từ file và tự động quét các file metadata.json."""
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

        # Tự động quét thêm từ các file metadata.json hiện có khi dùng file chính
        if self._path == SEEN_IDS_FILE:
            try:
                from config import PROJECT_ROOT
                for mf in PROJECT_ROOT.glob("Week*/*/metadata.json"):
                    try:
                        meta_records = json.loads(mf.read_text(encoding="utf-8"))
                        if isinstance(meta_records, list):
                            for r in meta_records:
                                if isinstance(r, dict) and "item_id" in r:
                                    self._seen.add(r["item_id"])
                    except Exception:
                        pass
                logger.info(f"Total cumulative active seen IDs: {len(self._seen)}")
            except Exception:
                pass

    def is_seen(self, item_id: str) -> bool:
        """Kiểm tra item_id đã được xử lý chưa. Hỗ trợ 3 dạng lookup."""
        with self._lock:
            if item_id in self._seen:
                return True

            # Tầng 2: Base ID (bỏ suffix _01)
            parts = item_id.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) <= 3:
                if parts[0] in self._seen:
                    return True

            # Tầng 3: Platform-specific raw ID (cách ly hoàn toàn TikTok và Facebook)
            if item_id.startswith("tt_") or item_id.startswith("fb_"):
                prefix = item_id[:3]
                raw_id = item_id[3:].split("_")[0]
                if raw_id.isdigit() and f"{prefix}{raw_id}" in self._seen:
                    return True
            elif item_id.isdigit():
                if f"tt_{item_id}" in self._seen or f"fb_{item_id}" in self._seen:
                    return True

            return False

    def mark_seen(self, item_id: str) -> None:
        """Đánh dấu item_id đã xử lý. Lưu đủ các dạng cùng platform để is_seen() nhận diện chính xác."""
        with self._lock:
            self._seen.add(item_id)  # Dạng đầy đủ: tt_7638091585464421652_01

            # Dạng base (bỏ suffix _01, _02, ...)
            parts = item_id.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) <= 3:
                base_id = parts[0]  # tt_7638091585464421652
                self._seen.add(base_id)

            # Dạng platform + raw id (giữ đúng platform prefix)
            prefix = "tt_" if item_id.startswith("tt_") else ("fb_" if item_id.startswith("fb_") else "")
            raw_id = item_id.removeprefix("tt_").removeprefix("fb_").split("_")[0]
            if raw_id.isdigit():
                self._seen.add(f"{prefix}{raw_id}")

            self._save_unlocked()

    def _save_unlocked(self) -> None:
        """Ghi atomic xuống file khi đang giữ lock."""
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

    def save(self) -> None:
        """Ghi danh sách seen_ids xuống file (atomic write)."""
        with self._lock:
            self._save_unlocked()
            logger.debug(f"Saved {len(self._seen)} seen IDs")

    def count(self) -> int:
        """Số lượng item_id đã thấy."""
        with self._lock:
            return len(self._seen)
