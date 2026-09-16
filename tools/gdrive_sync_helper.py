"""
tools/gdrive_sync_helper.py — Google Drive Sync & Packaging Helper for Cloud Separator.

Features:
  1. Auto-package cleaned Week1..4 folders into standalone zip archives.
  2. Generate verification checksums (MD5) for all zip archives.
  3. Upload/sync to Google Drive using gdown / rclone.
"""

from __future__ import annotations

import os
import sys
import json
import hashlib
import zipfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def calculate_md5(file_path: Path) -> str:
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def package_week(week_num: str, output_dir: Path) -> Path | None:
    w_name = f"Week{week_num}"
    src_dir = ROOT / w_name
    if not src_dir.exists():
        print(f"[-] Không tìm thấy thư mục {w_name}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{w_name}_Clean_Complete.zip"
    print(f"[+] Đang đóng gói {w_name} -> {zip_path.name} ...")

    file_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(ROOT)
                zf.write(full_path, rel_path)
                file_count += 1

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    md5_hash = calculate_md5(zip_path)
    print(f"  -> Hoàn tất {w_name}: {file_count} files | {size_mb:.1f} MB | MD5: {md5_hash}")
    return zip_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Google Drive Sync Helper")
    parser.add_argument("--package", choices=["1", "2", "3", "4", "all"], default="all", help="Package target week(s)")
    parser.add_argument("--out-dir", type=str, default=str(ROOT / "export_clean"), help="Output directory for archives")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    target_weeks = ["1", "2", "3", "4"] if args.package == "all" else [args.package]

    print("=" * 80)
    print("📦 BẮT ĐẦU ĐÓNG GÓI DỮ LIỆU ĐỂ ĐỒNG BỘ GOOGLE DRIVE")
    print("=" * 80)

    manifest = []
    for w in target_weeks:
        z_p = package_week(w, out_dir)
        if z_p:
            manifest.append({
                "week": f"Week{w}",
                "archive": z_p.name,
                "size_mb": round(z_p.stat().st_size / (1024 * 1024), 2),
                "md5": calculate_md5(z_p),
            })

    manifest_path = out_dir / "clean_export_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[+] Đã tạo manifest kiểm định tại: {manifest_path.name}")
    print("=" * 80)
    print("🎉 TẤT CẢ DỮ LIỆU ĐÃ SẴN SÀNG ĐỒNG BỘ LÊN GOOGLE DRIVE!")


if __name__ == "__main__":
    main()
