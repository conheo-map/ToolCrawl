#!/usr/bin/env python3
"""
main.py — Entry point cho Facebook & TikTok audio crawler.

Sử dụng:
  python main.py --platform tiktok --keyword "review quán ăn" --workers 4
  python main.py --platform facebook --keyword "học tiếng Việt" --max-results 500
  python main.py --platform tiktok --keyword "tin tức" --cookies cookies_tiktok.txt
  python main.py --platform tiktok --keyword "du lịch" --dry-run
"""

import argparse
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone, timedelta
from pathlib import Path

import config as cfg
from crawlers.tiktok import TikTokCrawler
from crawlers.facebook import FacebookCrawler
from processors.music_detector import MusicDetector
from processors.vocal_separator import VocalSeparator
from storage.dedup import DedupStore
from storage.metadata_writer import MetadataWriter
from storage.state_manager import StateManager
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.proxy_manager import ProxyManager

logger = get_logger("main")
VN_TZ = timezone(timedelta(hours=7))

# Graceful shutdown flag
_shutdown = False


def _handle_sigint(sig, frame):
    global _shutdown
    logger.warning("\nCtrl+C received — shutting down gracefully...")
    _shutdown = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Facebook & TikTok Vietnamese Speech Audio Crawler",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--platform", choices=["tiktok", "facebook"], required=True,
        help="Nền tảng cần crawl",
    )
    parser.add_argument(
        "--keyword", required=True,
        help="Keyword tìm kiếm (ví dụ: 'review quán ăn Hà Nội')",
    )
    parser.add_argument(
        "--max-results", type=int, default=500,
        help="Số video tối đa cần tìm kiếm",
    )
    parser.add_argument(
        "--region", choices=["auto", "northern", "southern", "central", "mixed"],
        default="auto",
        help="Gán nhãn vùng miền: northern (Bắc), southern (Nam), central (Trung), mixed (Hỗn hợp), auto (tự động)",
    )
    parser.add_argument(
        "--workers", type=int, default=cfg.MAX_WORKERS,
        help="Số worker thread song song",
    )
    parser.add_argument(
        "--week", type=int, default=cfg.WEEK_NUMBER,
        help="Số tuần (1-7)",
    )
    parser.add_argument(
        "--cookies", type=Path, default=None,
        help="Đường dẫn đến cookie file (.txt Netscape format)",
    )
    parser.add_argument(
        "--batch-num", type=int, default=1,
        help="Số thứ tự batch trong ngày",
    )
    parser.add_argument(
        "--skip-music-filter", action="store_true",
        help="Bỏ qua bước lọc nhạc nền",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Chỉ search và in URLs, không download",
    )
    return parser.parse_args()


def process_url(
    url: str,
    crawler,
    dedup: DedupStore,
    state: StateManager,
    writer: MetadataWriter,
    music_detector: MusicDetector,
    vocal_separator: VocalSeparator,
    batch_num: int,
    dry_run: bool = False,
    forced_region: str = "auto",
) -> str:
    """
    Xử lý một URL qua Pipeline Hybrid 3 Tầng:
      Tầng 1: Không có nhạc → lưu thẳng vào audio/ (fast path)
      Tầng 2: Có nhạc + Demucs khả dụng → AI tách giọng → lưu vào audio/
      Tầng 3: Có nhạc + Demucs không có → quarantine

    Trả về: 'done' | 'separated' | 'skipped' | 'rejected' | 'error'
    """
    global _shutdown
    if _shutdown:
        return "shutdown"

    # Check trạng thái từ checkpoint
    if state.is_done(url):
        logger.debug(f"Skipping (checkpoint): {url}")
        return "skipped"

    if dry_run:
        logger.info(f"[DRY-RUN] Would crawl: {url}")
        return "skipped"

    try:
        # Crawl URL
        record = crawler.crawl_url(url, batch_num=batch_num)
        if not record:
            writer.increment_error()
            state.add_failed(url, "crawl_url returned None")
            return "error"

        item_id = record["item_id"]

        # Override language_region nếu người dùng truyền flag --region
        if forced_region and forced_region != "auto":
            record["language_region"] = forced_region

        # Check dedup
        if dedup.is_seen(item_id):
            logger.debug(f"Duplicate: {item_id}")
            audio_path = cfg.AUDIO_DIR / f"{item_id}.wav"
            if audio_path.exists():
                audio_path.unlink(missing_ok=True)
            return "skipped"

        audio_path = cfg.AUDIO_DIR / f"{item_id}.wav"

        # ─── Pipeline Hybrid 3 Tầng ──────────────────────
        music_status = music_detector.process(audio_path=audio_path, metadata=record)

        if music_status == "clean":
            # Tầng 1: Audio sạch — lưu thẳng, không xử lý gì thêm
            record["vocal_separated"] = False
            record["clean_method"] = "original"
            logger.info(f"[Tầng 1] Clean audio: {item_id}")

        elif music_status == "music":
            if vocal_separator.available:
                # Tầng 2: Có nhạc → chạy AI Demucs tách giọng
                logger.info(f"[Tầng 2] Music detected, running Demucs AI: {item_id}")
                success = vocal_separator.separate(audio_path)
                if success:
                    record["vocal_separated"] = True
                    record["clean_method"] = "demucs_ai"
                    logger.info(f"[Tầng 2] Vocal separation successful: {item_id}")
                else:
                    # Demucs thất bại → quarantine để tránh dữ liệu kém chất lượng
                    logger.warning(f"[Tầng 2] Demucs failed, quarantining: {item_id}")
                    music_detector.quarantine(audio_path)
                    dedup.mark_seen(item_id)
                    state.mark_done(url)
                    return "rejected"
            else:
                # Tầng 3: Không có Demucs → quarantine
                logger.warning(f"[Tầng 3] No separator available, quarantining: {item_id}")
                music_detector.quarantine(audio_path)
                dedup.mark_seen(item_id)
                state.mark_done(url)
                return "rejected"
        # ─────────────────────────────────────────────────

        # Ghi metadata — xóa internal field trước khi ghi
        record.pop("_track", None)
        writer.add_record(record)
        dedup.mark_seen(item_id)
        state.mark_done(url)

        status_tag = "[AI-cleaned]" if record.get("vocal_separated") else "[clean]"
        logger.info(f"OK {status_tag} [{record.get('language_region', 'mixed')}]: {item_id} ({record['duration_seconds']:.1f}s)")
        return "done"

    except Exception as exc:
        logger.error(f"Error processing {url}: {exc}")
        writer.increment_error()
        state.add_failed(url, str(exc))
        return "error"


def main() -> None:
    args = parse_args()
    signal.signal(signal.SIGINT, _handle_sigint)

    logger.info(
        f"Starting {args.platform.upper()} crawler — "
        f"keyword='{args.keyword}' workers={args.workers} week={args.week}"
    )

    # Điều chỉnh week trong config (runtime override)
    if args.week != cfg.WEEK_NUMBER:
        cfg.WEEK_NUMBER = args.week
        cfg.BASE_OUTPUT_DIR = cfg.PROJECT_ROOT / f"Week{args.week}" / cfg.CRAWL_DATE
        cfg.AUDIO_DIR = cfg.BASE_OUTPUT_DIR / "audio"
        cfg.QUARANTINE_DIR = cfg.BASE_OUTPUT_DIR / "quarantine"
        cfg.METADATA_FILE = cfg.BASE_OUTPUT_DIR / "metadata.json"
        cfg.SUMMARY_FILE = cfg.BASE_OUTPUT_DIR / "summary.json"

    cfg.AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Override music filter nếu cần
    if args.skip_music_filter:
        cfg.MUSIC_FILTER_ENABLED = False

    # Cookie
    cookies = args.cookies
    if not cookies:
        cookies = (
            cfg.TIKTOK_COOKIES_FILE if args.platform == "tiktok"
            else cfg.FACEBOOK_COOKIES_FILE
        )

    # Khởi tạo components
    rate_limiter = RateLimiter()
    proxy_manager = ProxyManager()

    if args.platform == "tiktok":
        crawler = TikTokCrawler(
            cookies_file=cookies,
            rate_limiter=rate_limiter,
            proxy_manager=proxy_manager,
        )
    else:
        crawler = FacebookCrawler(
            cookies_file=cookies,
            rate_limiter=rate_limiter,
            proxy_manager=proxy_manager,
        )

    dedup = DedupStore()
    state = StateManager(platform=args.platform)
    writer = MetadataWriter(
        metadata_file=cfg.METADATA_FILE,
        summary_file=cfg.SUMMARY_FILE,
    )
    music_detector = MusicDetector(enabled=not args.skip_music_filter)
    vocal_separator = VocalSeparator()

    if vocal_separator.available:
        logger.info("Hybrid Pipeline: Demucs AI vocal separator ENABLED")
    else:
        logger.warning(
            "Hybrid Pipeline: Demucs not installed — music videos will be quarantined. "
            "Install with: pip install demucs"
        )

    # ─────────────────────────────────────────────
    # Step 1: Search
    # ─────────────────────────────────────────────
    logger.info(f"Searching '{args.keyword}' (max {args.max_results} results)...")
    urls = crawler.search(args.keyword, max_results=args.max_results)

    if not urls:
        logger.error("No URLs found. Check keyword or try adding cookies.")
        sys.exit(1)

    logger.info(f"Found {len(urls)} URLs. Starting download pipeline...")

    if args.dry_run:
        for url in urls:
            print(url)
        logger.info(f"[DRY-RUN] Listed {len(urls)} URLs. Exiting.")
        return

    # ─────────────────────────────────────────────
    # Step 2: Parallel download
    # ─────────────────────────────────────────────
    stats = {"done": 0, "skipped": 0, "rejected": 0, "error": 0}

    try:
        from tqdm import tqdm
        progress = tqdm(total=len(urls), desc="Crawling", unit="video")
    except ImportError:
        progress = None

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_url = {
            executor.submit(
                process_url,
                url, crawler, dedup, state, writer, music_detector, vocal_separator,
                args.batch_num, False, args.region,
            ): url
            for url in urls
        }

        for future in as_completed(future_to_url):
            if _shutdown:
                executor.shutdown(wait=False, cancel_futures=True)
                break

            result = future.result()
            if result in stats:
                stats[result] += 1

            if progress:
                progress.update(1)
                progress.set_postfix(stats)

    if progress:
        progress.close()

    # ─────────────────────────────────────────────
    # Step 3: Finalize
    # ─────────────────────────────────────────────
    dedup.save()
    writer.write_summary(platform=args.platform, batch_count=args.batch_num)

    logger.info(
        f"\n{'='*50}\n"
        f"DONE: {stats['done']} | "
        f"SKIPPED: {stats['skipped']} | "
        f"REJECTED (music): {stats['rejected']} | "
        f"ERRORS: {stats['error']}\n"
        f"Output: {cfg.BASE_OUTPUT_DIR}\n"
        f"{'='*50}"
    )


if __name__ == "__main__":
    main()
