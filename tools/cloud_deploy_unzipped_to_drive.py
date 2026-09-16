"""
tools/cloud_deploy_unzipped_to_drive.py — Deploy 100% Unzipped Clean Directory Tree to Google Drive & Cleanup Zips.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.cloud_turbo_separator import update_metadata_and_summary


def deploy_and_clean():
    weeks = ["Week1", "Week2", "Week3", "Week4"]

    print("\n" + "=" * 85)
    print("🚀 BẮT ĐẦU ĐỒNG BỘ CÂY THƯ MỤC GIẢI NÉN VÀ GHI ĐÈ LÊN GOOGLE DRIVE THEO CẤU TRÚC CŨ")
    print("=" * 85 + "\n")

    # Step 1: Chuẩn hóa metadata và summary cho toàn bộ các ngày
    print("[1/3] Đang chuẩn hóa 100% metadata.json và summary.json cho tất cả các tuần...")
    for w in weeks:
        w_dir = ROOT / w
        if not w_dir.exists():
            continue
        for day_dir in w_dir.iterdir():
            if day_dir.is_dir() and (day_dir / "audio").exists():
                update_metadata_and_summary(day_dir)
    print("[+] Đã chuẩn hóa xong metadata & summary 100%!\n")

    # Step 2: Upload cây thư mục giải nén ghi đè thẳng lên Drive
    print("[2/3] Đang đồng bộ từng file audio sạch + metadata.json + summary.json ghi đè vào thư mục cũ...")
    for w in weeks:
        src_path = ROOT / w
        if not src_path.exists():
            continue
        
        audio_count = len(list(src_path.glob("*/audio/*.wav")))
        if audio_count == 0:
            continue

        print(f"\n==================== ĐANG GHI ĐÈ {w} ({audio_count:,} files audio sạch) ====================")
        cmd = [
            "rclone", "copy",
            str(src_path), f"gdrive:{w}",
            "--update",
            "--transfers", "6",
            "--checkers", "6",
            "--tpslimit", "4",
            "--drive-pacer-min-sleep", "50ms",
            "-P",
        ]
        subprocess.run(cmd)

    # Step 3: Dọn dẹp các file zip trên Google Drive để Drive sạch sẽ 100%
    print("\n[3/3] Đang dọn dẹp các file .zip trên Google Drive...")
    for w in weeks:
        zip_name = f"{w}_clean_dataset.zip"
        print(f"  - Xóa {zip_name} khỏi gdrive:...")
        subprocess.run(["rclone", "deletefile", f"gdrive:{zip_name}"], capture_output=True)

    print("\n" + "=" * 85)
    print("🎉 HOÀN TẤT 100%! CÂY THƯ MỤC CŨ ĐÃ ĐƯỢC GHI ĐÈ SẠCH SẼ VÀ CÁC FILE ZIP ĐÃ ĐƯỢC XÓA KHỎI DRIVE!")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    deploy_and_clean()
