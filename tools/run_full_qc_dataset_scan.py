"""
tools/run_full_qc_dataset_scan.py — Quét tự động 100% kho dữ liệu (25,194 file)
bằng bộ tiêu chí 5 trụ cột ASR chuyên gia để phân loại thành 3 danh sách chính thức:
  1. tools/qc_results/keep_manifest.jsonl (KEEP / PASS)
  2. tools/qc_results/recrawl_manifest.jsonl (RECRAWL)
  3. tools/qc_results/delete_manifest.jsonl (DELETE)
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from tools.qc_asr_specialist_evaluator import analyze_audio_pillars

BASE_DIR = Path(".")
QC_OUT_DIR = BASE_DIR / "tools" / "qc_results"
QC_OUT_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_FILE = BASE_DIR / "tools" / "asr_training_corpus" / "data_manifest_asr_train.jsonl"

def run_scan():
    print("=" * 85)
    print("  QUÉT TỰ ĐỘNG TOÀN DIỆN KHO DỮ LIỆU BẰNG 5 TRỤ CỘT ASR CHUYÊN GIA")
    print("  (Ràng buộc thời lượng: Giữ nguyên độ dài cắt hiện tại [2.0s - 600.0s])")
    print("=" * 85)
    t0 = time.time()

    # 1. Nạp transcript
    manifest_map = {}
    if MANIFEST_FILE.exists():
        for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    obj = json.loads(line)
                    stem = Path(obj["audio_filepath"]).stem
                    manifest_map[stem] = obj.get("text", "")
                except Exception:
                    pass
    print(f"[*] Đã nạp {len(manifest_map):,} transcript từ manifest.")

    # 2. Tập hợp danh sách file cần quét
    all_tasks = []
    for mf in sorted(list(BASE_DIR.glob("Week*/*/metadata.json"))):
        d = mf.parent
        audio_dir = d / "audio"
        recs = json.loads(mf.read_text(encoding="utf-8"))
        for r in recs:
            iid = r["item_id"]
            wav_path = audio_dir / f"{iid}.wav"
            if wav_path.exists():
                text = manifest_map.get(iid, "")
                all_tasks.append((wav_path, text, r, f"{d.parent.name}/{d.name}"))

    total_files = len(all_tasks)
    print(f"[*] Tổng số tệp tin âm thanh cần thẩm định: {total_files:,} tệp.")

    # 3. Hàm xử lý 1 tệp
    def eval_one(item):
        wav_path, text, meta, date_rel = item
        score, decision, p_scores, det, reasons = analyze_audio_pillars(wav_path, text, meta)
        record = {
            "item_id": meta["item_id"],
            "platform": meta.get("platform", "tiktok"),
            "date_folder": date_rel,
            "relative_path": f"{date_rel}/audio/{meta['item_id']}.wav",
            "video_url": meta.get("video_url", ""),
            "duration_seconds": det.get("duration", meta.get("duration_seconds", 0)),
            "score": score,
            "decision": decision,
            "pillar_scores": p_scores,
            "reasons": reasons,
            "title": meta.get("title", ""),
            "language_region": meta.get("language_region", "mixed"),
            "transcript": text
        }
        return record

    print(f"[*] Đang thực thi thẩm định đa luồng (16 workers)...")
    results = []
    done_count = 0

    with ThreadPoolExecutor(max_workers=16) as pool:
        for rec in pool.map(eval_one, all_tasks):
            results.append(rec)
            done_count += 1
            if done_count % 2500 == 0 or done_count == total_files:
                print(f"  [{done_count:,}/{total_files:,}] ({done_count/total_files*100:.1f}%) "
                      f"Đã thẩm định {done_count:,} tệp ({time.time()-t0:.1f}s)...", flush=True)

    # 4. Phân tách thành 3 danh sách chính thức
    keep_list = []
    recrawl_list = []
    delete_list = []

    for r in results:
        dec = r["decision"]
        if dec == "KEEP":
            keep_list.append(r)
        elif dec == "RECRAWL":
            recrawl_list.append(r)
        else:
            delete_list.append(r)

    # 5. Ghi 3 file manifest JSONL
    f_keep = QC_OUT_DIR / "keep_manifest.jsonl"
    f_recrawl = QC_OUT_DIR / "recrawl_manifest.jsonl"
    f_delete = QC_OUT_DIR / "delete_manifest.jsonl"

    f_keep.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in keep_list), encoding="utf-8")
    f_recrawl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recrawl_list), encoding="utf-8")
    f_delete.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in delete_list), encoding="utf-8")

    # 6. Ghi báo cáo tổng hợp
    hours_keep = sum(r["duration_seconds"] for r in keep_list) / 3600.0
    hours_recrawl = sum(r["duration_seconds"] for r in recrawl_list) / 3600.0
    hours_delete = sum(r["duration_seconds"] for r in delete_list) / 3600.0

    summary_report = {
        "scan_time": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "total_files_audited": total_files,
        "total_hours_audited": round(sum(r["duration_seconds"] for r in results) / 3600.0, 2),
        "results": {
            "KEEP": {
                "count": len(keep_list),
                "percentage": round(len(keep_list) / total_files * 100, 2),
                "total_hours": round(hours_keep, 2),
                "description": "Đạt chuẩn ASR chất lượng cao, giữ trọn ngữ âm bản sắc"
            },
            "RECRAWL": {
                "count": len(recrawl_list),
                "percentage": round(len(recrawl_list) / total_files * 100, 2),
                "total_hours": round(hours_recrawl, 2),
                "description": "Phương ngữ/bài giảng quý nhưng bị over-denoised hoặc mép cắt cụt"
            },
            "DELETE": {
                "count": len(delete_list),
                "percentage": round(len(delete_list) / total_files * 100, 2),
                "total_hours": round(hours_delete, 2),
                "description": "Rác bán hàng, quảng cáo, TTS bot giả lập, không dùng cho ASR"
            }
        },
        "output_manifests": {
            "keep_manifest": str(f_keep),
            "recrawl_manifest": str(f_recrawl),
            "delete_manifest": str(f_delete)
        }
    }

    f_summary = QC_OUT_DIR / "qc_summary_report.json"
    f_summary.write_text(json.dumps(summary_report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 85)
    print("  KẾT QUẢ PHÂN LOẠI TOÀN BỘ KHO DỮ LIỆU:")
    print("=" * 85)
    print(f"  ✅ 1. KEEP (Giữ lại)  : {len(keep_list):,} file ({hours_keep:.2f}h) — {len(keep_list)/total_files*100:.2f}%")
    print(f"  🔄 2. RECRAWL (Cào lại): {len(recrawl_list):,} file ({hours_recrawl:.2f}h) — {len(recrawl_list)/total_files*100:.2f}%")
    print(f"  ❌ 3. DELETE (Xóa đi) : {len(delete_list):,} file ({hours_delete:.2f}h) — {len(delete_list)/total_files*100:.2f}%")
    print(f"\n[+] Đã lưu 3 danh sách chính thức tại thư mục: {QC_OUT_DIR}/")
    print(f"[+] Hoàn tất toàn bộ quy trình trong {time.time()-t0:.1f}s!")

if __name__ == "__main__":
    run_scan()
