"""
tools/cloud_sync_to_gdrive.py — 1-Click Sync Processed Audio, Metadata, and Summary to Google Drive.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from tools.cloud_turbo_separator import update_metadata_and_summary

ROOT = Path(__file__).resolve().parent.parent


def sync_all_weeks_to_drive(target_weeks: list[str] = None):
    if not target_weeks:
        target_weeks = ["Week1", "Week2", "Week3", "Week4"]

    print("\n" + "=" * 80)
    print("🚀 BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU ĐÃ TÁCH NHẠC LÊN GOOGLE DRIVE")
    print(f"Các tuần đồng bộ: {', '.join(target_weeks)}")
    print("=" * 80 + "\n")

    # Step 1: Chuẩn hóa metadata và summary cho toàn bộ các ngày đã tách
    print("[1/2] Đang cập nhật chuẩn hóa metadata.json và summary.json cho toàn bộ các ngày...")
    for w in target_weeks:
        w_dir = ROOT / w
        if not w_dir.exists():
            continue
        for day_dir in w_dir.iterdir():
            if day_dir.is_dir() and (day_dir / "audio").exists():
                update_metadata_and_summary(day_dir)
    print("[+] Hoàn tất cập nhật metadata.json & summary.json 100%!\n")

    # Step 2: Upload toàn bộ audio sạch + metadata.json + summary.json lên Drive qua Rclone
    print("[2/2] Đang tải lên Google Drive bằng Rclone...")
    for w in target_weeks:
        src_path = ROOT / w
        if not src_path.exists():
            print(f"[-] Bỏ qua {w} (thư mục chưa tồn tại trên máy)")
            continue

        audio_count = len(list(src_path.glob("*/audio/*.wav")))
        if audio_count == 0:
            print(f"[-] Bỏ qua {w} (chưa có file audio nào đã tách)")
            continue

        print(f"\n==================== ĐỒNG BỘ {w} ({audio_count:,} files audio sạch + metadata) ====================")
        cmd = [
            "rclone", "copy",
            str(src_path), f"gdrive:{w}",
            "--transfers", "16",
            "--checkers", "16",
            "--tpslimit", "8",
            "-P",
        ]
        subprocess.run(cmd)

    print("\n" + "=" * 80)
    print("🎉 TOÀN BỘ AUDIO SẠCH, METADATA.JSON VÀ SUMMARY.JSON ĐÃ ĐƯỢC ĐỒNG BỘ LÊN DRIVE 100%!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    w_arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    target = ["Week1", "Week2", "Week3", "Week4"] if w_arg == "all" else [w_arg]
    sync_all_weeks_to_drive(target)
