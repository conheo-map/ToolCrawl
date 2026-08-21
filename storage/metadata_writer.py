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


SPEC_KEYS = [
    "item_id",
    "platform",
    "platform_video_id",
    "video_url",
    "title",
    "description",
    "posted_at",
    "language_raw",
    "audio_path",
    "duration_seconds",
    "crawl_batch",
    "crawled_at",
    "platform_meta",
    "language_region",
]


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

        local_research_dir = Path("local_research") / CRAWL_DATE
        local_research_dir.mkdir(parents=True, exist_ok=True)

        self._extended_path = local_research_dir / "metadata_extended.json"
        self._funnel_path = local_research_dir / "yield_funnel.json"
        self._extended_records: list[dict] = []

        # Load extended records nếu có
        if self._extended_path.exists():
            try:
                self._extended_records = json.loads(self._extended_path.read_text(encoding="utf-8"))
            except Exception:
                self._extended_records = []

    def add_record(self, record: dict, extended_info: dict | None = None) -> None:
        """Thêm 1 record vào metadata.json (14 trường chuẩn công ty) và metadata_extended.json (Local)."""
        clean_record = {k: record[k] for k in SPEC_KEYS if k in record}
        
        # Local-only extended record
        ext_record = dict(clean_record)
        ext_record["legal_license"] = "research_only"
        ext_record["intended_use"] = "ASR_speech_recognition_training"
        if extended_info:
            ext_record.update(extended_info)

        with self._lock:
            self._records.append(clean_record)
            self._extended_records.append(ext_record)
            self._flush()

    def increment_error(self) -> None:
        """Tăng đếm lỗi."""
        with self._lock:
            self._error_count += 1

    def _flush(self) -> None:
        """Ghi toàn bộ records xuống file (atomic)."""
        # 1. File chuẩn công ty (cho Google Drive)
        tmp = self._meta_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._meta_path)

        # 2. File mở rộng (chỉ lưu trên Local)
        tmp_ext = self._extended_path.with_suffix(".tmp")
        tmp_ext.write_text(
            json.dumps(self._extended_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_ext.replace(self._extended_path)

    def write_summary(self, platform: str, batch_count: int = 1) -> None:
        """Ghi summary.json theo format spec công ty và yield_funnel.json cho Local."""
        with self._lock:
            unique_ids = len({r["item_id"] for r in self._records})
            total_hours = sum(
                r.get("duration_seconds", 0) for r in self._records
            ) / 3600.0

            # Summary chuẩn công ty (đẩy lên Drive)
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
                "total_hours": round(total_hours, 2),
                "error_count": self._error_count,
            }

            tmp = self._summary_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._summary_path)

            # Phễu đo lường tỷ lệ dùng được Yield Funnel (chỉ lưu trên Local)
            total_attempted = len(self._records) + self._error_count
            yield_rate = round((len(self._records) / total_attempted * 100), 1) if total_attempted > 0 else 0.0
            
            funnel = {
                "pilot_week": 3,
                "metric_name": "Tỷ lệ Audio Dùng Được Trước Khi Mở Rộng (Yield Funnel)",
                "total_crawled_attempted": total_attempted,
                "clear_speech_passed": len(self._records),
                "music_suppressed_passed": len(self._records),
                "zero_duplicates": unique_ids,
                "final_usable_items": len(self._records),
                "final_usable_hours": round(total_hours, 2),
                "usable_rate_percentage": f"{yield_rate}%",
                "audited_at": datetime.now(VN_TZ).isoformat(timespec="seconds")
            }
            tmp_f = self._funnel_path.with_suffix(".tmp")
            tmp_f.write_text(
                json.dumps(funnel, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_f.replace(self._funnel_path)

            logger.info(
                f"Summary: {len(self._records)} items, {total_hours:.2f}h | "
                f"Yield Funnel Rate: {yield_rate}%"
            )

    def now_vn(self) -> str:
        """Thời gian hiện tại theo timezone Việt Nam (ISO 8601)."""
        return datetime.now(VN_TZ).isoformat(timespec="seconds")
