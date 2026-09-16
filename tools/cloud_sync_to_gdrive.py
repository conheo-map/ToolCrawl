"""
tools/cloud_sync_to_gdrive.py — 1-Click Sync Processed Audio, Metadata, and Summary to Google Drive.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import time
import argparse
import subprocess
from tools.cloud_turbo_separator import update_metadata_and_summary


def sync_all_weeks_to_drive(target_weeks: list[str] = None):
    if not target_weeks:
        target_weeks = ["Week1", "Week2", "Week3", "Week4"]

    print("\n" + "=" * 80)
    print("🚀 BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU ĐÃ TÁCH NHẠC LÊN GOOGLE DRIVE (TỰ ĐỘNG BỎ QUA FILE ĐÃ CÓ)")
    print(f"Các tuần đồng bộ: {', '.join(target_weeks)}")
    print("=" * 80 + "\n")

    # Step 1: Chuẩn hóa metadata và summary cho toàn bộ các ngày đã tách
    print("[1/2] Đang cập nhật chuẩn hóa metadata.json và summary.json...")
    for w in target_weeks:
        w_dir = ROOT / w
        if not w_dir.exists():
            continue
        for day_dir in w_dir.iterdir():
            if day_dir.is_dir() and (day_dir / "audio").exists():
                update_metadata_and_summary(day_dir)
    print("[+] Hoàn tất cập nhật metadata.json & summary.json 100%!\n")

    # Step 2: Upload toàn bộ audio sạch + metadata.json + summary.json lên Drive qua Rclone
    print("[2/2] Đang đồng bộ lên Google Drive (chỉ đẩy file mới / bỏ qua file đã có)...")
    for w in target_weeks:
        src_path = ROOT / w
        if not src_path.exists():
            continue

        audio_count = len(list(src_path.glob("*/audio/*.wav")))
        if audio_count == 0:
            continue

        print(f"\n==================== ĐỒNG BỘ {w} ({audio_count:,} files audio sạch + metadata) ====================")
        cmd = [
            "rclone", "copy",
            str(src_path), f"gdrive:{w}",
            "--update",
            "--transfers", "16",
            "--checkers", "16",
            "--tpslimit", "8",
            "-P",
        ]
        subprocess.run(cmd)

    print("\n" + "=" * 80)
    print("🎉 HOÀN TẤT ĐỒNG BỘ LÊN GOOGLE DRIVE 100%!")
    print("=" * 80 + "\n")


def watch_and_sync_loop(target_weeks: list[str] = None, interval_sec: int = 60):
    print("=" * 85)
    print("🔄 CHẾ ĐỘ ĐỒNG BỘ SONG SONG TỰ ĐỘNG (REAL-TIME AUTO-SYNC)")
    print(f"Tab này sẽ tự động quét và tải lên các file mới tách sau mỗi {interval_sec} giây...")
    print("File nào đã tải lên rồi sẽ được BỎ QUA 100%, không bao giờ bị tải đè trùng lặp.")
    print("=" * 85 + "\n")

    while True:
        try:
            sync_all_weeks_to_drive(target_weeks)
            print(f"[*] Nghỉ {interval_sec}s trước lần đồng bộ tiếp theo (Bấm Ctrl+C để dừng)...", flush=True)
            time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n[+] Đã dừng chế độ đồng bộ tự động.")
            break
        except Exception as exc:
            print(f"[-] Lỗi đồng bộ: {exc}, thử lại sau {interval_sec}s...", flush=True)
            time.sleep(interval_sec)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloud GDrive Sync Tool")
    parser.add_argument("week", type=str, default="all", nargs="?", help="Week name e.g. Week1, Week2, all")
    parser.add_argument("--watch", action="store_true", help="Chạy đồng bộ liên tục song song trong khi tab kia đang tách nhạc")
    parser.add_argument("--interval", type=int, default=60, help="Thời gian lặp lại quét file mới (giây)")
    args = parser.parse_args()

    target = ["Week1", "Week2", "Week3", "Week4"] if args.week == "all" else [args.week]

    if args.watch:
        watch_and_sync_loop(target, interval_sec=args.interval)
    else:
        sync_all_weeks_to_drive(target)
