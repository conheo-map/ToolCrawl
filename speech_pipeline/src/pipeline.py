#!/usr/bin/env python3
"""
pipeline.py — Master Speech AI Data Pipeline Entrypoint
======================================================
Quy trình trọn gói: Crawl -> Audio Separation -> VAD Segmentation -> Dedup -> Gold Dataset.

Usage:
  python src/pipeline.py --urls urls.txt --model demucs --output dataset_demucs
  python src/pipeline.py --urls urls.txt --model melband --output dataset_melband
"""
import argparse
import json
import time
import sys
import io
from pathlib import Path
from tqdm import tqdm

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi bảng mã Unicode cp1252
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Đảm bảo Python luôn tìm thấy package 'src' dù chạy từ bất kỳ thư mục nào
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from src.crawler.tiktok_crawler import TikTokCrawler
from src.separation.demucs_engine import DemucsEngine
from src.separation.melband_engine import MelbandRoformerEngine
from src.vad_slicer.silero_slicer import SileroVADSlicer
from src.dedup.audio_dedup import AudioDedupEngine
from src.quality_gate.evaluator import QualityGateEvaluator




def run_full_pipeline(
    urls_file: Path,
    output_dir: Path,
    model_type: str = "demucs",
    device: str = None,
    limit: int = 0
):
    print("=" * 80)
    print(f"🚀 KHỞI ĐỘNG SPEECH DATA PIPELINE — MODEL: [{model_type.upper()}]")
    print(f"Đích xuất dữ liệu: {output_dir.resolve()}")
    print("=" * 80)

    # Khởi tạo thư mục làm việc
    raw_dir = output_dir / "01_raw"
    vocal_dir = output_dir / "02_vocal_clean"
    final_audio_dir = output_dir / "gold_dataset"
    final_audio_dir.mkdir(parents=True, exist_ok=True)

    # 1. Khởi tạo các Engine
    print("[*] Đang khởi tạo các mô hình AI...")
    crawler = TikTokCrawler(raw_dir=raw_dir)
    
    if model_type.lower() == "melband":
        separator = MelbandRoformerEngine(device=device)
    else:
        separator = DemucsEngine(device=device)

    slicer = SileroVADSlicer(min_segment_sec=3.0, max_segment_sec=15.0)
    dedup = AudioDedupEngine()
    evaluator = QualityGateEvaluator()

    # 2. Đọc URLs
    urls = [line.strip() for line in urls_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    if limit > 0:
        urls = urls[:limit]

    print(f"[*] Đã nạp {len(urls):,} URLs cần xử lý.\n")

    metadata_records = []
    stats = {
        "crawled": 0,
        "separated": 0,
        "sliced_segments": 0,
        "duplicates_removed": 0,
        "gold_approved": 0,
        "total_seconds": 0.0
    }

    # 3. Chạy Pipeline
    for idx, url in enumerate(tqdm(urls, desc="Pipeline Progress"), 1):
        # Bước 1: Crawl
        crawl_res = crawler.download_url(url)
        if not crawl_res:
            continue
        stats["crawled"] += 1

        # Bước 2: Tách nhạc AI (Demucs hoặc MelBand RoFormer)
        raw_path = crawl_res["audio_path"]
        vocal_path = vocal_dir / raw_path.name
        ok = separator.separate_vocal(raw_path, vocal_path)
        if not ok or not vocal_path.exists():
            continue
        stats["separated"] += 1

        # Bước 3: Silero VAD Slicing
        temp_slice_dir = output_dir / "temp_slice" / raw_path.stem
        segments = slicer.slice_file(vocal_path, temp_slice_dir)
        
        for seg in segments:
            stats["sliced_segments"] += 1
            seg_p = Path(seg["audio_path"])

            # Bước 4: Audio Fingerprint Deduplication
            is_dup, reason = dedup.is_duplicate(seg_p)
            if is_dup:
                stats["duplicates_removed"] += 1
                seg_p.unlink(missing_ok=True)
                continue

            # Bước 5: Quality Gate Evaluation
            q_metrics = evaluator.evaluate_audio(seg_p)
            
            # Di chuyển sang thư mục Gold Dataset (sử dụng replace để an toàn trên Windows)
            final_p = final_audio_dir / seg_p.name
            seg_p.replace(final_p)


            dur = q_metrics["duration_seconds"]
            stats["gold_approved"] += 1
            stats["total_seconds"] += dur

            record = {
                "audio_path": str(final_p.relative_to(output_dir)),
                "item_id": final_p.stem,
                "duration_seconds": dur,
                "spectral_flatness": q_metrics["spectral_flatness"],
                "snr_estimate_db": q_metrics["snr_db"],
                "source_url": url,
                "separation_model": model_type,
                "label": "research_only",
                "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
            metadata_records.append(record)

    # 4. Ghi metadata.jsonl
    meta_jsonl = output_dir / "metadata.jsonl"
    with open(meta_jsonl, "w", encoding="utf-8") as f:
        for r in metadata_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5. Báo cáo tổng kết
    total_hours = round(stats["total_seconds"] / 3600.0, 2)
    print("\n" + "=" * 80)
    print("📊 BÁO CÁO PHỄU DỮ LIỆU (DATA FUNNEL SUMMARY)")
    print("=" * 80)
    print(f"  1. URLs Input             : {len(urls):,}")
    print(f"  2. Tải thành công         : {stats['crawled']:,}")
    print(f"  3. Tách Vocal AI thành công: {stats['separated']:,}")
    print(f"  4. Tổng phân đoạn VAD     : {stats['sliced_segments']:,}")
    print(f"  5. Trùng lặp đã loại bỏ   : {stats['duplicates_removed']:,}")
    print(f"  🏆 GOLD DATASET HOÀN THIỆN: {stats['gold_approved']:,} audio files ({total_hours} Giờ)")
    print(f"  📁 Thư mục xuất           : {final_audio_dir}")
    print(f"  📄 Metadata JSONL         : {meta_jsonl}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Speech AI Data Pipeline")
    parser.add_argument("--urls", "-u", required=True, type=Path, help="File chứa danh sách URL")
    parser.add_argument("--output", "-o", required=True, type=Path, help="Thư mục xuất kết quả")
    parser.add_argument("--model", "-m", choices=["demucs", "melband"], default="demucs", help="Mô hình tách nhạc")
    parser.add_argument("--device", "-d", default=None, help="Device (cuda / cpu)")
    parser.add_argument("--limit", "-l", type=int, default=0, help="Giới hạn số URLs cào")
    args = parser.parse_args()

    run_full_pipeline(args.urls, args.output, args.model, args.device, args.limit)


if __name__ == "__main__":
    main()
