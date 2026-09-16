"""
tools/restructure_and_migrate_clean.py
Tái cấu trúc thư mục dataset:
1. Đổi tên Week1..4 -> Week1_cu..Week4_cu (Lưu trữ bản gốc)
2. Tạo mới Week1..4 rỗng
3. Sao chép cấu trúc ngày, metadata, summary và các file audio sạch (Nhóm 1 & 2: 1,484 files)
"""

from __future__ import annotations
import os, sys, json, shutil, time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent

weeks = ["Week1", "Week2", "Week3", "Week4"]
audit_files = {
    "Week1": ROOT / "local_research" / "audit_week1_full.json",
    "Week2": ROOT / "local_research" / "audit_week2_full.json",
    "Week3": ROOT / "local_research" / "audit_week3_full.json",
    "Week4": ROOT / "local_research" / "audit_week4_full.json",
}

print("="*85)
print("BƯỚC 1: TÁI CẤU TRÚC THƯ MỤC VÀ SAO CHÉP DỮ LIỆU SẠCH (NHÓM 1 & 2)")
print("="*85, flush=True)

# 1. Rename Week* -> Week*_cu
for w in weeks:
    old_dir = ROOT / w
    backup_dir = ROOT / f"{w}_cu"
    
    if old_dir.exists() and not backup_dir.exists():
        print(f"[+] Đổi tên: {w} -> {w}_cu ...", flush=True)
        old_dir.rename(backup_dir)
    elif backup_dir.exists():
        print(f"[i] Thư mục backup {w}_cu đã tồn tại sẵn.", flush=True)
        
    # Tạo thư mục Week* mới
    new_dir = ROOT / w
    new_dir.mkdir(parents=True, exist_ok=True)
    print(f"[+] Đã tạo thư mục dataset sạch mới: {w}", flush=True)

# 2. Sao chép cấu trúc và file Nhóm 1 & 2
total_copied_clean = 0
total_copied_meta = 0

for w in weeks:
    backup_dir = ROOT / f"{w}_cu"
    new_dir = ROOT / w
    af = audit_files.get(w)
    
    if not backup_dir.exists():
        print(f"[!] Không tìm thấy {backup_dir.name}, bỏ qua.", flush=True)
        continue
        
    print(f"\n--- Đang xử lý sao chép cho {w} ---", flush=True)
    
    # Đọc audit để lấy danh sách file Nhóm 1 & 2
    clean_items = set()
    if af and af.exists():
        with open(af, "r", encoding="utf-8") as f:
            audit_data = json.load(f)
        records = audit_data.get("records", [])
        for r in records:
            grp = str(r.get("group", "")).upper()
            if "NHOM_1" in grp or "NHOM_2" in grp or "GROUP_1" in grp or "GROUP_2" in grp:
                clean_items.add(r.get("item_id"))
        print(f"  [Audit] Tìm thấy {len(clean_items)} file thuộc Nhóm 1 & 2 trong {w}")
    
    # Duyệt qua các ngày trong backup_dir
    w_clean_count = 0
    for day_dir in backup_dir.iterdir():
        if not day_dir.is_dir():
            # Copy file cấp tuần (nếu có metadata.json hoặc summary.json)
            if day_dir.name in ["metadata.json", "summary.json"]:
                dst_meta = new_dir / day_dir.name
                shutil.copy2(day_dir, dst_meta)
                total_copied_meta += 1
            continue
            
        day_str = day_dir.name  # 2026-xx-xx
        new_day_dir = new_dir / day_str
        new_day_audio = new_day_dir / "audio"
        new_day_quarantine = new_day_dir / "quarantine"
        new_day_transcripts = new_day_dir / "transcripts"
        
        new_day_audio.mkdir(parents=True, exist_ok=True)
        new_day_quarantine.mkdir(parents=True, exist_ok=True)
        new_day_transcripts.mkdir(parents=True, exist_ok=True)
        
        # Copy metadata.json, summary.json, yield_funnel.json cấp ngày
        for mf in ["metadata.json", "summary.json", "yield_funnel.json"]:
            src_mf = day_dir / mf
            if src_mf.exists():
                shutil.copy2(src_mf, new_day_dir / mf)
                total_copied_meta += 1
                
        # Copy transcripts nếu có
        src_transcripts = day_dir / "transcripts"
        if src_transcripts.exists():
            for tf in src_transcripts.iterdir():
                if tf.is_file():
                    shutil.copy2(tf, new_day_transcripts / tf.name)
                    
        # Copy audio thuộc nhóm 1 & 2
        src_audio = day_dir / "audio"
        if src_audio.exists():
            for wav_f in src_audio.glob("*.wav"):
                # Extract item_id
                stem = wav_f.stem
                # Check if in clean_items
                if stem in clean_items or any(clean_id in stem for clean_id in clean_items):
                    dst_wav = new_day_audio / wav_f.name
                    shutil.copy2(wav_f, dst_wav)
                    w_clean_count += 1
                    total_copied_clean += 1
                    
    print(f"  -> Đã sao chép {w_clean_count} file audio sạch Nhóm 1 & 2 vào {w}/")

print("\n" + "="*85)
print(f"✅ HOÀN TẤT BƯỚC 1!")
print(f"  - Đã tái cấu trúc: Week1_cu, Week2_cu, Week3_cu, Week4_cu (Lưu trữ an toàn)")
print(f"  - Đã tạo mới: Week1, Week2, Week3, Week4 (Chứa cây thư mục sạch)")
print(f"  - Tổng số file audio sạch (Nhóm 1 & 2) đã sao chép: {total_copied_clean} files")
print(f"  - Tổng số file metadata/summary/cấu hình đã sao chép: {total_copied_meta} files")
print("="*85, flush=True)
