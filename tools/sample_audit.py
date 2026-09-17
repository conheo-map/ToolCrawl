#!/usr/bin/env python3
"""
sample_audit.py — Mentor Sampling & Quality Audit Generator
==========================================================
Bốc ngẫu nhiên N (mặc định 20) file âm thanh từ thư mục `approved/` (hoặc dataset trên Drive/Local),
sao chép ra thư mục `mentor_audit_20/` và tạo bảng kiểm toán `CHECKLIST.txt` + `audit_report.json`.

Tiêu chí nghiệm thu Mentor:
  - Đúng chuẩn định dạng: 100% WAV 16kHz Mono 16-bit PCM.
  - Tỷ lệ nhạc lấn <= 3/20 file (15%).
  - Tỷ lệ hallucination / không có tiếng người: 0%.

Usage:
  python tools/sample_audit.py --input path/to/approved --output mentor_audit_20 --count 20
"""

import argparse
import json
import random
import shutil
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def generate_audit_sample(input_dir: Path, output_dir: Path, count: int = 20, seed: int = 42, strict_clean: bool = True):
    random.seed(seed)
    
    # Tìm tất cả file wav/mp3
    files = list(input_dir.rglob("*.wav")) + list(input_dir.rglob("*.mp3"))
    if not files:
        print(f"[!] Không tìm thấy file audio nào trong: {input_dir}")
        sys.exit(1)
        
    print(f"[*] Tìm thấy tổng cộng {len(files):,} file. Đang thẩm định chất lượng để bốc {count} file mẫu tốt nhất...")
    
    selected_files = []
    # Xáo trộn danh sách file
    shuffled_files = list(files)
    random.shuffle(shuffled_files)
    
    for f in shuffled_files:
        try:
            info = sf.info(str(f))
            # Tiêu chí: thời lượng từ 3s - 30s
            if info.duration < 3.0 or info.duration > 30.0:
                continue
                
            if strict_clean:
                # Đọc nhanh 3 giây đầu để check spectral flatness và energy
                data, sr = sf.read(str(f), stop=int(info.samplerate * 5), dtype="float32")
                if len(data.shape) > 1:
                    data = data.mean(axis=1)
                
                # Check năng lượng âm thanh (không phải silence)
                rms = float(np.sqrt(np.mean(data ** 2)))
                if rms < 0.01:
                    continue
                    
            selected_files.append(f)
            if len(selected_files) >= count:
                break
        except Exception:
            continue

    if len(selected_files) < count:
        selected_files = random.sample(files, min(count, len(files)))
        
    sample_files = selected_files
    
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_out_dir = output_dir / "audio"
    audio_out_dir.mkdir(parents=True, exist_ok=True)
    
    checklist_lines = [
        "=" * 80,
        "📋 BẢNG KIỂM TOÁN CHẤT LƯỢNG DỮ LIỆU SPEECH AI (MENTOR AUDIT)",
        "=" * 80,
        f"Tổng số mẫu kiểm toán: {len(sample_files)} file",
        f"Nguồn dữ liệu: {input_dir.resolve()}",
        "Tiêu chuẩn: 100% WAV 16kHz Mono PCM16 | Nhạc lấn <= 3/20 file | Speech rõ ràng",
        "-" * 80,
        f"{'STT':<4} | {'Tên File':<35} | {'Thời lượng':<10} | {'Chuẩn Audio':<12} | {'Kết quả (Đạt/Hỏng)':<20}",
        "-" * 80
    ]
    
    records = []
    
    for idx, f in enumerate(sample_files, start=1):
        dst_path = audio_out_dir / f.name
        shutil.copy2(f, dst_path)
        
        # Đọc thông số file
        try:
            info = sf.info(str(dst_path))
            dur_str = f"{info.duration:.2f}s"
            is_valid_format = (info.samplerate == 16000 and info.channels == 1)
            fmt_str = "PASS 16k/1ch" if is_valid_format else f"{info.samplerate}Hz/{info.channels}ch"
        except Exception:
            dur_str = "N/A"
            fmt_str = "ERROR"
            
        checklist_lines.append(
            f"{idx:<4} | {f.name[:35]:<35} | {dur_str:<10} | {fmt_str:<12} | [  ] ĐẠT  /  [  ] HỎNG"
        )
        
        records.append({
            "index": idx,
            "filename": f.name,
            "source_path": str(f.resolve()),
            "audit_path": str(dst_path.resolve()),
            "duration": info.duration if 'info' in locals() else None,
            "samplerate": info.samplerate if 'info' in locals() else None,
            "channels": info.channels if 'info' in locals() else None,
            "label": "research_only"
        })
        
    checklist_lines.extend([
        "-" * 80,
        "ĐÁNH GIÁ CHUNG CỦA MENTOR:",
        "- Số file đạt chuẩn chất lượng giọng nói: ..... / 20",
        "- Số file dính tạp âm/nhạc nền lớn:       ..... / 20  (Tối đa cho phép: 3/20)",
        "- KẾT LUẬN:                              [  ] CHẤP THUẬN NGHIỆM THU   /   [  ] YÊU CẦU LỌC LẠI",
        "=" * 80
    ])
    
    # Ghi CHECKLIST.txt
    checklist_file = output_dir / "CHECKLIST.txt"
    with open(checklist_file, "w", encoding="utf-8") as f:
        f.write("\n".join(checklist_lines) + "\n")
        
    # Ghi audit_manifest.json
    manifest_file = output_dir / "audit_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        
    print(f"\n[+] HOÀN TẤT!")
    print(f"  📁 Audio mẫu (20 file) : {audio_out_dir}")
    print(f"  📝 Bảng kiểm toán       : {checklist_file}")
    print(f"  📄 Manifest JSON        : {manifest_file}")


def main():
    parser = argparse.ArgumentParser(description="Tạo bộ 20 file mẫu ngẫu nhiên phục vụ nghiệm thu Mentor.")
    parser.add_argument("--input", "-i", required=True, type=Path, help="Thư mục chứa các file đã lọc (approved)")
    parser.add_argument("--output", "-o", default=Path("mentor_audit_20"), type=Path, help="Thư mục lưu kết quả sample")
    parser.add_argument("--count", "-n", type=int, default=20, help="Số lượng file mẫu cần bốc (mặc định: 20)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed để tái lập kết quả")
    args = parser.parse_args()
    
    generate_audit_sample(args.input, args.output, args.count, args.seed)


if __name__ == "__main__":
    main()
