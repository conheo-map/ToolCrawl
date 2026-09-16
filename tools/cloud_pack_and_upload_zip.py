"""
tools/cloud_pack_and_upload_zip.py — Ultra-Fast Zero-Throttle Bulk Zip Pack & GDrive Upload.
Packs processed clean audio + metadata.json + summary.json into .zip archives and uploads to Drive in seconds.
"""

from __future__ import annotations

import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.cloud_turbo_separator import update_metadata_and_summary


def pack_and_upload_week(target_week: str):
    w_clean = target_week if target_week.startswith("Week") else f"Week{target_week}"
    src_dir = ROOT / w_clean

    if not src_dir.exists():
        print(f"[-] Bỏ qua {w_clean} (thư mục chưa tồn tại)")
        return

    # 1. Chuẩn hóa metadata và summary
    print(f"\n[*] [1/3] Đang cập nhật metadata.json & summary.json cho {w_clean}...", flush=True)
    for day_dir in src_dir.iterdir():
        if day_dir.is_dir() and (day_dir / "audio").exists():
            update_metadata_and_summary(day_dir)

    # 2. Nén toàn bộ thư mục thành file zip
    zip_path = ROOT / f"{w_clean}_clean_dataset"
    print(f"[*] [2/3] Đang đóng gói nén ZIP {w_clean}...", flush=True)
    shutil.make_archive(str(zip_path), "zip", root_dir=str(ROOT), base_dir=w_clean)
    final_zip = ROOT / f"{w_clean}_clean_dataset.zip"
    zip_size_mb = final_zip.stat().st_size / (1024 * 1024)
    print(f"[+] Đóng gói thành công: {final_zip.name} ({zip_size_mb:.1f} MB)", flush=True)

    # 3. Tải file ZIP lên Google Drive qua Rclone (siêu tốc ~150MB/s)
    print(f"[*] [3/3] Đang tải {final_zip.name} lên Google Drive (gdrive:)...", flush=True)
    cmd = [
        "rclone", "copy",
        str(final_zip), "gdrive:",
        "--drive-chunk-size", "32M",
        "--timeout", "10m",
        "--retries", "5",
        "-P",
    ]
    subprocess.run(cmd)
    print(f"🎉 HOÀN TẤT ĐẨY {final_zip.name} LÊN GOOGLE DRIVE 100%!\n", flush=True)


def main():
    w_arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    target_weeks = ["Week1", "Week2", "Week3", "Week4"] if w_arg == "all" else [w_arg]

    print("=" * 85)
    print("🚀 BẮT ĐẦU ĐÓNG GÓI NÉN ZIP & ĐẨY LÊN GOOGLE DRIVE SIÊU TỐC (ZERO RATE LIMIT)")
    print(f"Tuần: {', '.join(target_weeks)}")
    print("=" * 85)

    for w in target_weeks:
        pack_and_upload_week(w)

    print("=" * 85)
    print("🎉 TOÀN BỘ CÁC TUẦN ĐÃ ĐƯỢC ĐÓNG GÓI VÀ TẢI LÊN GOOGLE DRIVE THÀNH CÔNG RỰC RỠ!")
    print("=" * 85)


if __name__ == "__main__":
    main()
