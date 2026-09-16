"""
tools/audit_bgm_tri_group.py — Quét kiểm toán BGM tại chỗ (Read-Only / Không chỉnh sửa audio).

Phân loại chính xác 3 nhóm:
  - NHÓM 1: Audio Thực Sự Sạch (Clean Speech: music_prob < 0.30)
  - NHÓM 2: 620 File Đã Từng Cố Gắng Tách Bằng Bộ Lọc Cũ (vocal_separated = True)
  - NHÓM 3: Audio Dính Nhạc Nhưng Bị "Lọt Lưới" (music_prob >= 0.30)
      + 3A: BGM vừa (0.30 <= prob < 0.70)
      + 3B: BGM nặng (prob >= 0.70)
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from processors.music_detector import MusicDetector


def analyze_single_file(args_tuple):
    wav_path_str, is_group2 = args_tuple
    wav_path = Path(wav_path_str)
    
    if is_group2:
        return {
            "item_id": wav_path.stem,
            "path": wav_path_str,
            "group": "NHOM_2_SEPARATED_SPECTRAL",
            "music_prob": 1.0,
            "note": "Đã bị xử lý bằng bộ lọc spectral cơ bản cũ",
        }
    
    # Phân tích sóng âm đa cửa sổ
    md = MusicDetector()
    is_music, prob = md.analyze(wav_path)
    
    if prob >= 0.70:
        grp = "NHOM_3B_LEAKED_HEAVY_BGM"
    elif prob >= 0.30:
        grp = "NHOM_3A_LEAKED_MODERATE_BGM"
    else:
        grp = "NHOM_1_GENUINELY_CLEAN"
        
    return {
        "item_id": wav_path.stem,
        "path": wav_path_str,
        "group": grp,
        "music_prob": round(prob, 4),
    }


def run_audit(target_dir: Path, output_file: Path, max_workers: int = 8, limit: int | None = None):
    print(f"[*] Bắt đầu quét kiểm toán tại: {target_dir}")
    t0 = time.time()
    
    # 1. Thu thập danh sách metadata để nhận diện Nhóm 2
    group2_ids = set()
    metadata_files = list(target_dir.glob("**/metadata.json"))
    for mf in metadata_files:
        try:
            records = json.loads(mf.read_text(encoding="utf-8"))
            for r in records:
                if r.get("vocal_separated") is True:
                    group2_ids.add(r.get("item_id"))
        except Exception:
            pass

    # 2. Thu thập danh sách audio files
    wav_files = list(target_dir.glob("**/audio/*.wav"))
    if limit:
        wav_files = wav_files[:limit]
        
    print(f"[*] Tổng số file WAV cần quét: {len(wav_files)}")
    print(f"[*] Số file thuộc Nhóm 2 (Metadata đánh dấu tách cũ): {len(group2_ids)}")

    tasks = [(str(w), w.stem in group2_ids) for w in wav_files]

    results = {
        "summary": {
            "target_dir": str(target_dir),
            "total_files_scanned": len(wav_files),
            "nhom_1_clean_count": 0,
            "nhom_2_separated_old_count": 0,
            "nhom_3_leaked_bgm_count": 0,
            "nhom_3a_moderate_bgm": 0,
            "nhom_3b_heavy_bgm": 0,
            "scan_duration_sec": 0,
        },
        "records": []
    }

    # Chạy song song đa tiến trình
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for idx, res in enumerate(executor.map(analyze_single_file, tasks), 1):
            grp = res["group"]
            if grp == "NHOM_1_GENUINELY_CLEAN":
                results["summary"]["nhom_1_clean_count"] += 1
            elif grp == "NHOM_2_SEPARATED_SPECTRAL":
                results["summary"]["nhom_2_separated_old_count"] += 1
            elif grp == "NHOM_3A_LEAKED_MODERATE_BGM":
                results["summary"]["nhom_3_leaked_bgm_count"] += 1
                results["summary"]["nhom_3a_moderate_bgm"] += 1
            elif grp == "NHOM_3B_LEAKED_HEAVY_BGM":
                results["summary"]["nhom_3_leaked_bgm_count"] += 1
                results["summary"]["nhom_3b_heavy_bgm"] += 1

            results["records"].append(res)
            if idx % 100 == 0 or idx == len(tasks):
                print(f"    -> Đã quét {idx}/{len(tasks)} files ({idx/len(tasks)*100:.1f}%)...")

    results["summary"]["scan_duration_sec"] = round(time.time() - t0, 2)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    s = results["summary"]
    tot = s["total_files_scanned"]
    print("\n" + "=" * 60)
    print("BÁO CÁO KIỂM TOÁN TẠI CHỖ (READ-ONLY AUDIT)")
    print("=" * 60)
    print(f"Tổng số file quét:                     {tot}")
    print(f"1. NHÓM 1: Audio Thật Sự Sạch:        {s['nhom_1_clean_count']} ({s['nhom_1_clean_count']/max(tot,1)*100:.1f}%)")
    print(f"2. NHÓM 2: Đã Cố Tách Nhưng Bị Hỏng:   {s['nhom_2_separated_old_count']} ({s['nhom_2_separated_old_count']/max(tot,1)*100:.1f}%)")
    print(f"3. NHÓM 3: Dính Nhạc Bị Lọt Lưới:      {s['nhom_3_leaked_bgm_count']} ({s['nhom_3_leaked_bgm_count']/max(tot,1)*100:.1f}%)")
    print(f"   - Nhóm 3A (BGM vừa 0.30 - 0.70):   {s['nhom_3a_moderate_bgm']}")
    print(f"   - Nhóm 3B (BGM nặng >= 0.70):      {s['nhom_3b_heavy_bgm']}")
    print(f"Thời gian quét:                        {s['scan_duration_sec']} giây")
    print(f"File kết quả chi tiết:                 {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Audit BGM Tri-Group Scan")
    parser.add_argument("--dir", type=str, required=True, help="Thư mục cần quét kiểm toán")
    parser.add_argument("--output", type=str, default="local_research/audit_bgm_report.json")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run_audit(Path(args.dir), Path(args.output), max_workers=args.workers, limit=args.limit)


if __name__ == "__main__":
    main()
