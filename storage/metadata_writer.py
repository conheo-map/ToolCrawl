"""
storage/metadata_writer.py — Thread-safe ghi metadata.json và summary.json.
"""

import json
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from utils.logger import get_logger
from config import (
    METADATA_FILE,
    SUMMARY_FILE,
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    AUDIO_FORMAT,
    AUDIO_CODEC,
    CRAWL_DATE,
)

logger = get_logger("metadata_writer")

VN_TZ = timezone(timedelta(hours=7))


class MetadataWriter:
    """
    Ghi record từng item vào metadata.json (JSON array).
    Cập nhật summary.json sau mỗi batch.
    Thread-safe.
    """

    def __init__(
        self,
        metadata_file: Path = METADATA_FILE,
        summary_file: Path = SUMMARY_FILE,
    ) -> None:
        self._meta_path = metadata_file
        self._summary_path = summary_file
        self._lock = threading.Lock()
        self._records: list[dict] = []
        self._error_count: int = 0

        # Tạo thư mục nếu chưa có
        metadata_file.parent.mkdir(parents=True, exist_ok=True)

        # Load records hiện có (resume từ session trước)
        if self._meta_path.exists():
            try:
                existing = json.loads(
                    self._meta_path.read_text(encoding="utf-8")
                )
                self._records = existing if isinstance(existing, list) else []
                logger.info(
                    f"Loaded {len(self._records)} existing records "
                    f"from {self._meta_path.name}"
                )
            except Exception as exc:
                logger.warning(f"Could not load existing metadata: {exc}")

    def add_record(self, record: dict) -> None:
        """Thêm 1 record vào metadata.json (thread-safe)."""
        with self._lock:
            self._records.append(record)
            self._flush()

    def increment_error(self) -> None:
        """Tăng đếm lỗi."""
        with self._lock:
            self._error_count += 1

    def _flush(self) -> None:
        """Ghi toàn bộ records xuống file (atomic). Gọi khi đang giữ lock."""
        tmp = self._meta_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._meta_path)

    def write_summary(self, platform: str, batch_count: int = 1) -> None:
        """Ghi summary.json theo format spec."""
        with self._lock:
            unique_ids = len({r["item_id"] for r in self._records})
            total_hours = sum(
                r.get("duration_seconds", 0) for r in self._records
            ) / 3600.0

            vocal_sep_count = sum(1 for r in self._records if r.get("vocal_separated"))

            summary = {
                "platform": platform,
                "crawl_date": CRAWL_DATE,
                "batch_count": batch_count,
                "audio_spec": {
                    "sample_rate": AUDIO_SAMPLE_RATE,
                    "channels": AUDIO_CHANNELS,
                    "format": f"{AUDIO_FORMAT}_{AUDIO_CODEC}",
                },
                "items_delivered": len(self._records),
                "unique_item_ids": unique_ids,
                "vocal_separated_count": vocal_sep_count,
                "total_hours": round(total_hours, 2),
                "error_count": self._error_count,
            }

            tmp = self._summary_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._summary_path)
            logger.info(
                f"Summary: {len(self._records)} items, "
                f"{total_hours:.2f}h, {self._error_count} errors"
            )

    def now_vn(self) -> str:
        """Thời gian hiện tại theo timezone Việt Nam (ISO 8601)."""
        return datetime.now(VN_TZ).isoformat(timespec="seconds")
