"""
tools/check_cloud_progress.py — Quick Progress & Audit Inspector for RunPod Cloud Pipeline.
Checks downloaded source files (*_cu) and finished separated files for Week1..Week4.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def check_progress():
    weeks = ["Week1", "Week2", "Week3", "Week4"]
    
    print("\n" + "=" * 80)
    print("📊 BÁO CÁO TIẾN ĐỘ DỮ LIỆU & BÓC TÁCH ÂM THANH TRÊN RUNPOD")
    print("=" * 80)
    print(f"{'TUẦN':<10} | {'ĐÃ TẢI TỪ DRIVE (_cu)':<25} | {'ĐÃ TÁCH XONG (sạch)':<22} | {'TIẾN ĐỘ TÁCH'}")
    print("-" * 80)

    total_downloaded = 0
    total_separated = 0

    for w in weeks:
        src_dir = ROOT / f"{w}_cu"
        dst_dir = ROOT / w

        # Count downloaded files
        src_files = list(src_dir.glob("*/audio/*.wav")) if src_dir.exists() else []
        src_count = len(src_files)
        total_downloaded += src_count

        # Count separated files
        dst_files = list(dst_dir.glob("*/audio/*.wav")) if dst_dir.exists() else []
        dst_count = len(dst_files)
        total_separated += dst_count

        pct = (dst_count / max(1, src_count)) * 100 if src_count > 0 else 0.0
        pct_str = f"{pct:6.1f}%" if src_count > 0 else "0.0% (chưa tải)"

        print(f"{w:<10} | {src_count:>10,} files ({w}_cu)     | {dst_count:>10,} files ({w})    | {pct_str}")

    print("=" * 80)
    total_pct = (total_separated / max(1, total_downloaded)) * 100 if total_downloaded > 0 else 0.0
    print(f"{'TỔNG CỘNG':<10} | {total_downloaded:>10,} files            | {total_separated:>10,} files            | {total_pct:6.1f}%")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    check_progress()
