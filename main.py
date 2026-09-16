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
from processors.audio_enhancer import SpeechEnhancer
from processors.speech_transcriber import SpeechTranscriber
from processors.quality_assessor import QualityAssessor
from processors.audio_slicer import AudioSlicer
from processors.content_guard import ContentGuard
from processors.synthetic_speech_detector import SyntheticSpeechDetector  # [MOI - Diem Nghen #7]
from storage.dedup import DedupStore
from storage.metadata_writer import MetadataWriter
from storage.state_manager import StateManager
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.proxy_manager import ProxyManager
from utils.cookie_manager import CookieManager

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
        help="Số luồng download song song",
    )
    parser.add_argument(
        "--week", type=int, default=cfg.WEEK_NUMBER,
        help="Tuần crawl (1-7)",
    )
    parser.add_argument(
        "--cookies", type=Path, default=None,
        help="Đường dẫn file cookies.txt",
    )
    parser.add_argument(
        "--batch-num", type=int, default=1,
        help="Số thứ tự batch trong ngày",
    )
    parser.add_argument(
        "--skip-music-filter", action="store_true",
        help="Tắt bộ lọc nhạc (crawl tất cả video)",
    )
    parser.add_argument(
        "--sync-drive", action="store_true",
        help="Đồng bộ dữ liệu lên Google Drive sau khi cào (mặc định: TẮT)",
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
    speech_enhancer: SpeechEnhancer | None = None,
    speech_transcriber: SpeechTranscriber | None = None,
    quality_assessor: QualityAssessor | None = None,
    audio_slicer: AudioSlicer | None = None,
    content_guard: ContentGuard | None = None,
) -> str:
    """
    Xử lý một URL qua Pipeline Hybrid 3 Tầng & Speech Enhancement:
      Tầng 1: Không có nhạc → lưu thẳng vào audio/ (fast path)
      Tầng 2: Có nhạc + Demucs khả dụng → AI tách giọng → lưu vào audio/
      Tầng 3: Có nhạc + Demucs không có → quarantine
      Tầng 4: Tăng cường độ rõ phụ âm, khử tạp âm nền & cân bằng âm lượng to/nhỏ (Dynamic Leveling)
      Tầng 5: Cắt audio thành các phân đoạn 5s - 30s chuẩn ASR theo khoảng lặng
      Tầng 6: Sinh transcript tiếng Việt nháp ~70% (Lưu vào transcripts/ trên Local)

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
            state.mark_done(url)
            return "rejected"

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
        _crawl_date = (record.get("crawled_at") or cfg.CRAWL_DATE)[:10]

        # ─── Pipeline Hybrid 3 Tang ──────────────────────
        # [UPGRADE 2.2] process() gio tra ve (status, music_prob) tuple
        music_status, music_prob = music_detector.process(audio_path=audio_path, metadata=record)
        record["music_prob"] = round(music_prob, 4)  # Ghi vao metadata

        if music_status == "clean":
            # Tang 1: Audio sach — luu thang, khong xu ly gi them
            record["vocal_separated"] = False
            record["clean_method"] = "original"
            logger.info(f"[Tang 1] Clean audio (music_prob={music_prob:.3f}): {item_id}")

        elif music_status == "music":
            if vocal_separator.available:
                # Tang 2: Co nhac -> chay AI Demucs tach giong
                logger.info(f"[Tang 2] Music detected (prob={music_prob:.3f}), running Demucs AI: {item_id}")
                success = vocal_separator.separate(audio_path)
                if success:
                    # ─── [SMART GATE] Tái kiểm tra độ sạch sau khi tách ───
                    post_is_music, post_music_prob = music_detector.analyze(audio_path)
                    if post_music_prob > 0.20:
                        logger.warning(
                            f"[Post-Separation Gate] Tàn dư BGM sau khi tách vẫn quá lớn "
                            f"(prob={post_music_prob:.3f} > 0.20) -> Loại bỏ vào Quarantine: {item_id}"
                        )
                        music_detector.quarantine(audio_path, crawl_date=_crawl_date)
                        dedup.mark_seen(item_id)
                        state.mark_done(url)
                        return "rejected"

                    record["vocal_separated"] = True
                    record["clean_method"] = "demucs_ai"
                    record["post_separation_music_prob"] = round(post_music_prob, 4)
                    logger.info(f"[Tang 2] Vocal separation verified CLEAN (residual prob={post_music_prob:.3f}): {item_id}")
                else:
                    # Demucs that bai -> quarantine
                    logger.warning(f"[Tang 2] Demucs failed, quarantining: {item_id}")
                    music_detector.quarantine(audio_path, crawl_date=_crawl_date)  # [FIX 1.1]
                    dedup.mark_seen(item_id)
                    state.mark_done(url)
                    return "rejected"
            else:
                # Tang 3: Khong co Demucs -> quarantine
                logger.warning(f"[Tang 3] No separator available, quarantining: {item_id}")
                music_detector.quarantine(audio_path, crawl_date=_crawl_date)  # [FIX 1.1]
                dedup.mark_seen(item_id)
                state.mark_done(url)
                return "rejected"

        # ─── [MOI - Diem Nghen #7] Synthetic Speech Detection ──────────
        if cfg.SSD_ENABLED:
            _ssd = SyntheticSpeechDetector()
            synthetic_prob, synth_tag = _ssd.analyze(audio_path)
            record["synthetic_prob"] = round(synthetic_prob, 4)
            record["synth_method"]   = synth_tag

            if synthetic_prob > cfg.SSD_PROB_REJECT:
                logger.warning(
                    f"[SSD] TTS/Synthetic detected (prob={synthetic_prob:.3f}) "
                    f"-> Quarantining: {item_id}"
                )
                _ssd.quarantine(audio_path, crawl_date=_crawl_date)
                writer.increment_quarantine()
                dedup.mark_seen(item_id)
                state.mark_done(url)
                return "rejected"
            elif synthetic_prob > cfg.SSD_PROB_FLAG:
                logger.warning(
                    f"[SSD] Possibly synthetic (prob={synthetic_prob:.3f}) "
                    f"-> Flagged but kept: {item_id}"
                )
                # Giu lai nhung danh dau de human review
        # ──────────────────────────────────────────────────────────────


        # ─── Tăng cường âm thanh ASR: Làm rõ chữ, lọc tạp âm & cân bằng âm lượng to/nhỏ ───
        if speech_enhancer:
            if speech_enhancer.enhance(audio_path):
                from processors.audio_converter import verify_audio
                try:
                    final_info = verify_audio(audio_path)
                    record["duration_seconds"] = final_info["duration_seconds"]
                except Exception as e:
                    logger.warning(f"Failed to recalculate duration for {item_id}: {e}")

        # ─── Cắt phân đoạn ASR thông minh (Smart ASR Slicer: 5s - 30s) ───
        slices = []
        if audio_slicer:
            slices = audio_slicer.slice_audio(audio_path, item_id, output_dir=cfg.AUDIO_DIR)

        if not slices:
            slices = [{
                "item_id": item_id,
                "audio_path": audio_path,
                "duration_seconds": record.get("duration_seconds", 30.0),
                "segment_index": 1,
                "total_segments": 1,
            }]

        total_accepted_slices = 0
        for seg in slices:
            seg_item_id = seg["item_id"]
            seg_audio_path = seg["audio_path"]
            seg_duration = seg["duration_seconds"]

            seg_record = dict(record)
            seg_record["item_id"] = seg_item_id
            seg_record["duration_seconds"] = seg_duration
            seg_record["audio_path"] = f"audio/{cfg.CRAWL_DATE}/{seg_audio_path.name}" if hasattr(cfg, "CRAWL_DATE") else f"audio/{seg_audio_path.name}"

            # Thẩm định Chất lượng Âm thanh ASR (SNR & Quality Score)
            extended_data = {}
            if quality_assessor:
                q_stats = quality_assessor.assess(seg_audio_path)
                extended_data["snr_db"] = q_stats["snr_db"]
                extended_data["quality_score"] = q_stats["quality_score"]
                extended_data["speech_ratio"] = q_stats["speech_ratio"]
                extended_data["peak_dbfs"] = q_stats["peak_dbfs"]

                if not q_stats["is_clean"] and q_stats["snr_db"] < cfg.MUSIC_SNR_HARD_REJECT_DB:
                    logger.warning(
                        f"[Quality Guard] Audio degraded "
                        f"(SNR={q_stats['snr_db']}dB < {cfg.MUSIC_SNR_HARD_REJECT_DB}dB) "
                        f"-> Quarantining: {seg_item_id}"
                    )
                    # [FIX 1.1] Dùng get_quarantine_dir với ngày crawl gốc
                    music_detector.quarantine(seg_audio_path, crawl_date=_crawl_date)
                    dedup.mark_seen(seg_item_id)
                    continue

            # ─── BỘ LỌC ÂM HỌC TỪNG PHÂN ĐOẠN (Post-Slice Acoustic Gate) ───
            if music_detector and music_detector.is_music(seg_audio_path):
                logger.warning(f"[Post-Slice Gate] Music/Outro detected in slice -> Quarantining: {seg_item_id}")
                music_detector.quarantine(seg_audio_path, crawl_date=_crawl_date)
                dedup.mark_seen(seg_item_id)
                continue

            # Sinh Transcript Nháp Tiếng Việt (Chỉ lưu trên Local)
            if speech_transcriber:
                trans_info = speech_transcriber.transcribe_file(
                    seg_audio_path,
                    output_dir=Path("local_research") / cfg.CRAWL_DATE / "transcripts"
                )
                text_content = (trans_info.get("text") or "").strip()
                wc = trans_info.get("word_count", len(text_content.split()))
                no_speech_prob = trans_info.get("no_speech_prob", 0.0)

                # ─── HARD ASR GATE: Chặn triệt để file rỗng / outro không lời / tạp âm ───
                if wc < 3 or no_speech_prob > 0.50:
                    logger.warning(
                        f"[Hard ASR Gate] Non-speech / empty slice (words={wc}, no_speech={no_speech_prob:.2f}) -> Quarantining: {seg_item_id}"
                    )
                    music_detector.quarantine(seg_audio_path, crawl_date=_crawl_date)
                    dedup.mark_seen(seg_item_id)
                    continue

                if text_content:
                    extended_data["transcript_raw"] = text_content
                    extended_data["transcript_word_count"] = wc

                    # ─── BỘ LỌC NỘI DUNG THÔNG MINH (ContentGuard) ───
                    if content_guard:
                        c_decision = content_guard.classify(text_content, metadata=seg_record)
                        extended_data["content_category"] = c_decision.category
                        extended_data["content_decision"] = c_decision.action
                        if c_decision.action == "REJECT":
                            logger.warning(
                                f"[ContentGuard REJECT] {seg_item_id}: {c_decision.reason} -> Quarantining"
                            )
                            music_detector.quarantine(seg_audio_path, crawl_date=_crawl_date)
                            dedup.mark_seen(seg_item_id)
                            continue

            # Ghi nhận các trường phân tích nâng cao vào extended metadata
            extended_data["music_prob"] = record.get("music_prob", 0.0)
            extended_data["synthetic_prob"] = record.get("synthetic_prob", 0.0)
            extended_data["synth_method"] = record.get("synth_method", "real")

            # Ghi metadata — metadata.json (chuẩn 14 trường Drive) và metadata_extended.json (Local)
            seg_record.pop("_track", None)
            writer.add_record(seg_record, extended_info=extended_data)
            dedup.mark_seen(seg_item_id)
            total_accepted_slices += 1

        dedup.mark_seen(item_id)
        state.mark_done(url)

        status_tag = "[AI-cleaned]" if record.get("vocal_separated") else "[clean]"
        logger.info(f"OK {status_tag} [{record.get('language_region', 'mixed')}]: {item_id} -> {total_accepted_slices} ASR segment(s)")
        return "done" if total_accepted_slices > 0 else "rejected"

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
    cookie_manager = CookieManager(cookie_input=cookies, platform=args.platform)

    if args.platform == "tiktok":
        crawler = TikTokCrawler(
            cookies_file=cookies,
            rate_limiter=rate_limiter,
            proxy_manager=proxy_manager,
            cookie_manager=cookie_manager,
        )
    else:
        crawler = FacebookCrawler(
            cookies_file=cookies,
            rate_limiter=rate_limiter,
            proxy_manager=proxy_manager,
            cookie_manager=cookie_manager,
        )

    dedup = DedupStore()
    state = StateManager(platform=args.platform)
    writer = MetadataWriter(
        metadata_file=cfg.METADATA_FILE,
        summary_file=cfg.SUMMARY_FILE,
    )
    music_detector = MusicDetector(enabled=not args.skip_music_filter)
    vocal_separator = VocalSeparator()
    speech_enhancer = SpeechEnhancer()
    speech_transcriber = SpeechTranscriber()
    quality_assessor = QualityAssessor()
    try:
        from processors.vad_slicer import VadSlicer
        audio_slicer = VadSlicer()
    except Exception as e:
        logger.warning(f"Could not load VadSlicer ({e}), falling back to AudioSlicer")
        audio_slicer = AudioSlicer()
    content_guard = ContentGuard()
    synthetic_detector = SyntheticSpeechDetector()  # [MOI - Diem Nghen #7]

    if vocal_separator.available:
        logger.info("Hybrid Pipeline: Demucs AI vocal separator ENABLED")
    else:
        logger.warning(
            "Hybrid Pipeline: Demucs not installed — music videos will be quarantined. "
            "Install with: pip install demucs"
        )
    logger.info("ASR Speech Enhancer: Studio DSP filter & EBU R128 (-16 LUFS) ACTIVE")
    logger.info(f"Smart Audio Slicer: Natural pause-based ASR segmenter (5s - 30s) ACTIVE [{'Silero VAD' if getattr(audio_slicer, 'available', False) else 'FFmpeg Silence'}]")
    logger.info("Quality Assessor: Industrial ASR SNR & Speech Quality Verifier ACTIVE")
    logger.info("Speech Transcriber: Automated draft Vietnamese transcription (Step 05) ACTIVE")
    logger.info("Content Guard: Industrial Domain Classifier (News/Law/Education Rejector) ACTIVE")
    logger.info(
        f"Synthetic Speech Detector: TTS/VoiceClone detection (Diem Nghen #7) "
        f"{'ACTIVE' if cfg.SSD_ENABLED else 'DISABLED'}"
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
                args.batch_num, False, args.region, speech_enhancer, speech_transcriber,
                quality_assessor, audio_slicer, content_guard,
            ): url
            for url in urls
        }

        for future in as_completed(future_to_url):
            if _shutdown:
                executor.shutdown(wait=False, cancel_futures=True)
                break

            try:
                result = future.result()
            except Exception as exc:
                url = future_to_url.get(future, "unknown")
                logger.error(f"Worker exception for {url}: {exc}")
                result = "error"

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
    writer.write_summary(platform=args.platform, batch_count=args.batch_num, audio_dir=cfg.AUDIO_DIR)

    logger.info(
        f"\n{'='*50}\n"
        f"DONE: {stats['done']} | "
        f"SKIPPED: {stats['skipped']} | "
        f"REJECTED (music): {stats['rejected']} | "
        f"ERRORS: {stats['error']}\n"
        f"Output: {cfg.BASE_OUTPUT_DIR}\n"
        f"{'='*50}"
    )

    # ─────────────────────────────────────────────
    # Step 4: Đồng bộ lên Google Drive (Mặc định: TẮT)
    # ─────────────────────────────────────────────
    if getattr(args, "sync_drive", False):
        sync_to_gdrive(args.week)
    else:
        logger.info("ℹ️ Tự động đồng bộ Google Drive đang TẮT. Để đồng bộ, thêm cờ --sync-drive.")


def sync_to_gdrive(week_number: int) -> None:
    """Tự động đẩy dữ liệu sang Google Drive tốc độ cao với 8 luồng song song."""
    import shutil
    import subprocess
    if not shutil.which("rclone"):
        return
    
    week_dir = cfg.PROJECT_ROOT / f"Week{week_number}"
    # 0. Tự động đối soát 100% giữa file audio thực tế và metadata trước khi đẩy
    try:
        from tools.reconcile_drive import reconcile_folder
        for d in week_dir.iterdir():
            if d.is_dir() and (d / "audio").exists():
                reconcile_folder(d)
    except Exception as exc:
        logger.debug(f"Pre-sync reconcile notice: {exc}")

    gdrive_target = f"gdrive,root_folder_id=16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw:Week{week_number}/"
    # Tính toán timeout động dựa trên số lượng file audio thực tế
    total_wav_count = len(list(week_dir.glob("**/*.wav")))
    # Ước lượng: tối thiểu 3600s (1 tiếng), hoặc 15 giây/file + buffer
    dynamic_timeout = max(3600, total_wav_count * 15)
    logger.info(f"📤 Đang đồng bộ toàn bộ {week_dir.name} ({total_wav_count} audio files) lên Google Drive (8 luồng song song, timeout {dynamic_timeout // 60} phút)...")

    try:
        # Chạy rclone đa luồng an toàn với rate-limit pacer chống lỗi Google 403 Quota Exceeded
        cmd = [
            "rclone", "copy", str(week_dir), gdrive_target,
            "--exclude", "transcripts/**",
            "--exclude", "metadata_extended.json",
            "--exclude", "yield_funnel.json",
            "--exclude", "quarantine/**",
            "--transfers", "8",
            "--checkers", "16",
            "--tpslimit", "8",
            "--drive-pacer-min-sleep", "100ms",
            "--drive-pacer-burst", "50",
            "--retries", "5",
            "--low-level-retries", "10",
            "--drive-chunk-size", "32M",
            "--stats", "15s",
        ]
        res = subprocess.run(
            cmd,
            capture_output=False,  # In trực tiếp tiến độ ra màn hình
            timeout=dynamic_timeout,  # Co giãn theo số lượng file
        )
        if res.returncode == 0:
            logger.info("✅ ĐÃ ĐỒNG BỘ AUDIO LÊN GOOGLE DRIVE! ĐANG ĐỐI SOÁT CUMULATIVE CUỐI CÙNG...")
            try:
                from tools.reconcile_drive import reconcile_remote_drive
                reconcile_remote_drive(week_number=week_number)
            except Exception as e:
                logger.debug(f"Post-sync remote reconcile error: {e}")
            logger.info("🎉 ĐÃ HOÀN TẤT ĐỒNG BỘ 100% TOÀN BỘ AUDIO, METADATA VÀ SUMMARY TRÊN GOOGLE DRIVE!")
        else:
            logger.warning(f"Rclone sync kết thúc với mã: {res.returncode}")
    except subprocess.TimeoutExpired:
        logger.warning(f"⚠️ Quá thời gian timeout ({dynamic_timeout // 60} phút). Vui lòng chạy 'python tools/reconcile_drive.py --remote' để tiếp tục phần còn lại.")
    except Exception as exc:
        logger.debug(f"Rclone sync exception: {exc}")


if __name__ == "__main__":
    main()
