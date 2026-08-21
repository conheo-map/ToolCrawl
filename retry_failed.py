#!/usr/bin/env python3
"""
retry_failed.py — Retry các video lỗi từ phiên crawl trước.

Sử dụng:
  python retry_failed.py --platform tiktok --date 2026-08-18
  python retry_failed.py --platform facebook
"""

import argparse
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import config as cfg
from crawlers.tiktok import TikTokCrawler
from crawlers.facebook import FacebookCrawler
from processors.music_detector import MusicDetector
from storage.dedup import DedupStore
from storage.metadata_writer import MetadataWriter
from storage.state_manager import StateManager
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.proxy_manager import ProxyManager

logger = get_logger("retry_failed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retry failed downloads",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--platform", choices=["tiktok", "facebook"], required=True,
    )
    parser.add_argument(
        "--date", default=cfg.CRAWL_DATE,
        help="Ngày crawl (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--workers", type=int, default=2,
        help="Số worker (giảm để tránh block)",
    )
    parser.add_argument("--cookies", type=Path, default=None)
    return parser.parse_args()


def load_failed_urls(platform: str, date: str) -> list[dict]:
    """Load danh sách URL lỗi từ JSONL file."""
    error_file = cfg.ERRORS_DIR / f"failed_{date}.jsonl"
    if not error_file.exists():
        logger.warning(f"No error file found: {error_file}")
        return []

    records = []
    with open(error_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("platform") == platform:
                    records.append(record)
            except json.JSONDecodeError:
                continue

    logger.info(f"Loaded {len(records)} failed records for {platform} on {date}")
    return records


def main() -> None:
    args = parse_args()
    failed_records = load_failed_urls(args.platform, args.date)

    if not failed_records:
        logger.info("No failed records to retry. Exiting.")
        return

    # Khởi tạo với delay cao hơn (tránh block khi retry)
    rate_limiter = RateLimiter(min_sec=3.0, max_sec=8.0)
    proxy_manager = ProxyManager()

    if args.platform == "tiktok":
        crawler = TikTokCrawler(
            cookies_file=args.cookies,
            rate_limiter=rate_limiter,
            proxy_manager=proxy_manager,
        )
    else:
        crawler = FacebookCrawler(
            cookies_file=args.cookies,
            rate_limiter=rate_limiter,
            proxy_manager=proxy_manager,
        )

    dedup = DedupStore()
    state = StateManager(platform=args.platform)
    writer = MetadataWriter(
        metadata_file=cfg.METADATA_FILE,
        summary_file=cfg.SUMMARY_FILE,
    )
    music_detector = MusicDetector()

    # Lọc bỏ records đã thành công
    to_retry = [
        r for r in failed_records
        if not state.is_done(r["url"]) and not dedup.is_seen(r["item_id"])
    ]

    logger.info(f"Retrying {len(to_retry)} URLs with {args.workers} workers...")

    from processors.vocal_separator import VocalSeparator
    from processors.audio_enhancer import SpeechEnhancer
    from processors.speech_transcriber import SpeechTranscriber
    from main import process_url, sync_to_gdrive

    vocal_separator = VocalSeparator()
    speech_enhancer = SpeechEnhancer()
    speech_transcriber = SpeechTranscriber()

    stats = {"done": 0, "skipped": 0, "rejected": 0, "error": 0}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_url,
                r["url"], crawler, dedup, state, writer,
                music_detector, vocal_separator, 1, False, None,
                speech_enhancer, speech_transcriber,
            ): r
            for r in to_retry
        }

        for future in as_completed(futures):
            result = future.result()
            if result in stats:
                stats[result] += 1

    dedup.save()
    writer.write_summary(platform=args.platform, batch_count=1, audio_dir=cfg.AUDIO_DIR)
    sync_to_gdrive(week_number=cfg.WEEK_NUMBER)

    logger.info(
        f"Retry complete: done={stats['done']} skipped={stats['skipped']} "
        f"rejected={stats['rejected']} error={stats['error']}"
    )

    # Cleanup: xóa records đã done khỏi error file
    error_file = cfg.ERRORS_DIR / f"failed_{args.date}.jsonl"
    if error_file.exists():
        remaining = []
        with open(error_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if not state.is_done(record.get("url", "")):
                        remaining.append(line)
                except json.JSONDecodeError:
                    remaining.append(line)
        with open(error_file, "w", encoding="utf-8") as f:
            for line in remaining:
                f.write(line + "\n")
        logger.info(f"Cleaned error file: {len(remaining)} remaining failures")


if __name__ == "__main__":
    main()
