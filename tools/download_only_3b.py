"""
tools/download_only_3b.py — Download ONLY Group 3B files from Google Drive via Rclone.
"""

from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def download_group_3b(target_week: str = "Week3"):
    w_clean = target_week if target_week.startswith("Week") else f"Week{target_week}"
    w_num = w_clean.replace("Week", "")
    audit_file = ROOT / "local_research" / f"audit_week{w_num}_full.json"

    if not audit_file.exists():
        print(f"[-] Không tìm thấy file audit {audit_file.name}")
        return

    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    recs = audit.get("records", [])
    target_3b_ids = {
        r["item_id"] for r in recs
        if "3b" in str(r.get("group", "")).lower() or "heavy" in str(r.get("group", "")).lower()
    }

    print(f"[*] Tổng số file Nhóm 3B cần tải cho {w_clean}: {len(target_3b_ids):,} files", flush=True)

    print(f"[*] Đang lấy danh sách file từ gdrive:{w_clean} qua Rclone (vài giây)...", flush=True)
    cmd_lsf = ["rclone", "lsf", f"gdrive:{w_clean}", "-R", "--files-only"]
    res = subprocess.run(cmd_lsf, capture_output=True, text=True)

    if res.returncode != 0:
        print(f"[-] Lỗi rclone lsf: {res.stderr}")
        return

    all_remote_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    print(f"[+] Tìm thấy tổng cộng {len(all_remote_files):,} files trên gdrive:{w_clean}", flush=True)

    files_to_download = []
    for f in all_remote_files:
        p = Path(f)
        if p.name.endswith(".wav"):
            item_id = p.stem
            if item_id in target_3b_ids:
                files_to_download.append(f)
        elif p.name in ("metadata.json", "summary.json"):
            files_to_download.append(f)

    print(f"[+] Đã lọc chính xác {len(files_to_download):,} files thuộc NHÓM 3B (kèm metadata/summary)", flush=True)

    list_file = ROOT / f"files_3b_{w_clean.lower()}.txt"
    list_file.write_text("\n".join(files_to_download), encoding="utf-8")

    dst_dir = ROOT / f"{w_clean}_cu"
    dst_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🚀 Bắt đầu tải siêu tốc {len(files_to_download):,} files nhóm 3B về {dst_dir}...\n", flush=True)
    cmd_copy = [
        "rclone", "copy",
        f"gdrive:{w_clean}", str(dst_dir),
        "--files-from", str(list_file),
        "--transfers", "16",
        "--checkers", "16",
        "--tpslimit", "8",
        "-P",
    ]
    subprocess.run(cmd_copy)
    print(f"\n🎉 HOÀN TẤT TẢI NHÓM 3B CHO {w_clean} 100%!")


if __name__ == "__main__":
    w_arg = sys.argv[1] if len(sys.argv) > 1 else "Week3"
    download_group_3b(w_arg)
