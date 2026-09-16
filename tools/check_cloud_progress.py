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


import json
import argparse


def check_progress(filter_group: str = "all"):
    weeks = ["Week1", "Week2", "Week3", "Week4"]
    
    print("\n" + "=" * 85)
    print(f"📊 BÁO CÁO TIẾN ĐỘ DỮ LIỆU & BÓC TÁCH TRÊN RUNPOD (NHÓM: {filter_group.upper()})")
    print("=" * 85)
    print(f"{'TUẦN':<10} | {'ĐÃ TẢI TỪ DRIVE (_cu)':<25} | {'ĐÃ TÁCH XONG (sạch)':<22} | {'TIẾN ĐỘ TÁCH'}")
    print("-" * 85)

    total_downloaded = 0
    total_separated = 0

    for w in weeks:
        w_num = w.replace("Week", "")
        audit_file = ROOT / "local_research" / f"audit_week{w_num}_full.json"
        rec_map = {}
        if audit_file.exists():
            try:
                audit = json.loads(audit_file.read_text(encoding="utf-8"))
                rec_map = {r["item_id"]: str(r.get("group", "")).lower() for r in audit.get("records", [])}
            except Exception:
                pass

        src_dir = ROOT / f"{w}_cu"
        dst_dir = ROOT / w

        # Count downloaded files
        src_files = list(src_dir.glob("*/audio/*.wav")) if src_dir.exists() else []
        if filter_group == "3b" and rec_map:
            src_files = [f for f in src_files if "3b" in rec_map.get(f.stem, "") or "heavy" in rec_map.get(f.stem, "")]
        elif filter_group == "3a" and rec_map:
            src_files = [f for f in src_files if "3a" in rec_map.get(f.stem, "") or "moderate" in rec_map.get(f.stem, "")]
        
        src_count = len(src_files)
        total_downloaded += src_count

        # Count separated files
        dst_files = list(dst_dir.glob("*/audio/*.wav")) if dst_dir.exists() else []
        if filter_group == "3b" and rec_map:
            dst_files = [f for f in dst_files if "3b" in rec_map.get(f.stem, "") or "heavy" in rec_map.get(f.stem, "")]
        elif filter_group == "3a" and rec_map:
            dst_files = [f for f in dst_files if "3a" in rec_map.get(f.stem, "") or "moderate" in rec_map.get(f.stem, "")]
        
        dst_count = len(dst_files)
        total_separated += dst_count

        pct = (dst_count / max(1, src_count)) * 100 if src_count > 0 else 0.0
        pct_str = f"{pct:6.1f}%" if src_count > 0 else "0.0% (chưa có)"

        print(f"{w:<10} | {src_count:>10,} files ({w}_cu)     | {dst_count:>10,} files ({w})    | {pct_str}")

    print("=" * 85)
    total_pct = (total_separated / max(1, total_downloaded)) * 100 if total_downloaded > 0 else 0.0
    print(f"{'TỔNG CỘNG':<10} | {total_downloaded:>10,} files            | {total_separated:>10,} files            | {total_pct:6.1f}%")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=["3a", "3b", "all"], default="all", help="Group to inspect")
    args = parser.parse_args()
    check_progress(args.group)
