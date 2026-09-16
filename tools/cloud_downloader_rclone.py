"""
tools/cloud_downloader_rclone.py — Ultra-Reliable Rclone Downloader for Cloud Pod.
Uses local rclone binary with optimal flags to download directly from Drive remote.
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    week = sys.argv[1] if len(sys.argv) > 1 else "Week3"
    w_clean = week if week.startswith("Week") else f"Week{week}"
    
    print(f"[*] Đang kiểm tra danh sách folder trên Google Drive bằng Rclone...")
    res = subprocess.run(["rclone", "lsd", "gdrive:"], capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(f"[Log] {res.stderr}")

    dst = ROOT / f"{w_clean}_cu"
    dst.mkdir(parents=True, exist_ok=True)
    
    print(f"\n[+] Bắt đầu tải {w_clean} từ gdrive:{w_clean} về {dst}...")
    cmd = [
        "rclone", "copy",
        f"gdrive:{w_clean}", str(dst),
        "--transfers", "16",
        "--checkers", "16",
        "--tpslimit", "8",
        "-P",
    ]
    subprocess.run(cmd)

if __name__ == "__main__":
    main()
