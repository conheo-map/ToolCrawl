"""
crawl_topic.py — Runner tự động cào theo Chuyên đề / Kênh tuyển chọn.
Sử dụng cho cả Local và GitHub Actions Matrix Cloud.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
from pathlib import Path
from utils.logger import get_logger
import config as cfg

logger = get_logger("crawl_topic")
CONFIG_PATH = cfg.PROJECT_ROOT / "config" / "curated_channels.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Chuyên đề Audio Crawler Runner")
    parser.add_argument(
        "--topic",
        choices=["news_national", "regional_dialects", "education_podcast", "life_interview", "all"],
        default="news_national",
        help="Chuyên đề cần cào dữ liệu",
    )
    parser.add_argument("--platform", choices=["tiktok", "facebook"], default="tiktok")
    parser.add_argument("--workers", type=int, default=4, help="Số luồng song song")
    parser.add_argument("--max-per-channel", type=int, default=20, help="Số video tối đa mỗi kênh")
    parser.add_argument("--max-per-keyword", type=int, default=30, help="Số video tối đa mỗi keyword")
    return parser.parse_args()


def run_single_topic(topic_key: str, topic_data: dict, platform: str, workers: int, max_ch: int, max_kw: int):
    import subprocess
    name = topic_data.get("name", topic_key)
    channels = topic_data.get("channels", [])
    keywords = topic_data.get("keywords", [])

    logger.info(f"\n{'='*60}\n🚀 BẮT ĐẦU CHUYÊN ĐỀ: {name.upper()}\n{'='*60}")

    # 1. Cào từ các Kênh tuyển chọn
    for ch_url in channels:
        logger.info(f"🎙️ [Kênh] Đang cào: {ch_url} (tối đa {max_ch} video)")
        cmd = [
            sys.executable, "main.py",
            "--platform", platform,
            "--keyword", ch_url,
            "--max-results", str(max_ch),
            "--workers", str(workers),
        ]
        try:
            subprocess.run(cmd, timeout=900)
        except Exception as e:
            logger.warning(f"Lỗi khi cào kênh {ch_url}: {e}")

    # 2. Cào từ các Từ khóa chuyên đề
    for kw in keywords:
        logger.info(f"🔎 [Từ khóa] Đang tìm kiếm: '{kw}' (tối đa {max_kw} video)")
        cmd = [
            sys.executable, "main.py",
            "--platform", platform,
            "--keyword", kw,
            "--max-results", str(max_kw),
            "--workers", str(workers),
        ]
        try:
            subprocess.run(cmd, timeout=900)
        except Exception as e:
            logger.warning(f"Lỗi khi cào từ khóa '{kw}': {e}")


def main():
    args = parse_args()
    if not CONFIG_PATH.exists():
        logger.error(f"Không tìm thấy cấu hình kênh tại: {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if args.topic == "all":
        for k, v in data.items():
            run_single_topic(k, v, args.platform, args.workers, args.max_per_channel, args.max_per_keyword)
    else:
        if args.topic not in data:
            logger.error(f"Chuyên đề '{args.topic}' không tồn tại trong cấu hình.")
            sys.exit(1)
        run_single_topic(args.topic, data[args.topic], args.platform, args.workers, args.max_per_channel, args.max_per_keyword)

    logger.info("🎉 HOÀN THÀNH PHIÊN CÀO CHUYÊN ĐỀ!")


if __name__ == "__main__":
    main()
