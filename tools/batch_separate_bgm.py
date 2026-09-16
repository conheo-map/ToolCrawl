"""
tools/batch_separate_bgm.py — Tach nhac nen hang loat bang Demucs AI cho Dataset ASR.

Tinh nang:
  1. Ho tro chia nho thanh cac batch (mỗi batch N file) va luu checkpoint lien tuc.
  2. Che do test doi chung (--test-eval N): luu copy truoc (before) va sau (after) de nghe tham dinh.
  3. Post-separation gate: do lai music_prob sau khi tach, dam bao chi giu audio <= 0.20 music_prob.
  4. Cap nhat truc tiep vao metadata.json cua ngay tuong ung.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Fix sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from processors.music_detector import MusicDetector
from processors.vocal_separator import VocalSeparator, DEFAULT_MODEL
from utils.logger import get_logger

logger = get_logger("batch_separator")

CHECKPOINT_PATH = PROJECT_ROOT / "local_research" / "separation_checkpoint.json"


def load_audit_files(phase: str = "all") -> list[dict]:
    """Doc danh sach cac file can tach tu cac file audit json."""
    audit_files = [
        PROJECT_ROOT / "local_research" / "audit_week1_full.json",
        PROJECT_ROOT / "local_research" / "audit_week2_full.json",
        PROJECT_ROOT / "local_research" / "audit_week3_full.json",
        PROJECT_ROOT / "local_research" / "audit_week4_full.json",
    ]

    target_groups = set()
    if phase == "3b":
        target_groups = {"NHOM_3B_HEAVY_BGM"}
    elif phase == "3a":
        target_groups = {"NHOM_3A_MODERATE_BGM"}
    elif phase == "2":
        target_groups = {"NHOM_2_SEPARATED_OLD"}
    else:
        target_groups = {"NHOM_3B_HEAVY_BGM", "NHOM_3A_MODERATE_BGM", "NHOM_2_SEPARATED_OLD"}

    items_to_process = []
    seen_ids = set()

    # Index all local wav files quickly
    print("[*] Dang lap chi muc vi tri cac file WAV tren dia...", flush=True)
    wav_index = {}
    for p in PROJECT_ROOT.glob("Week*/**/audio/*.wav"):
        wav_index[p.stem] = p

    for af in audit_files:
        if not af.exists():
            continue
        try:
            data = json.loads(af.read_text(encoding="utf-8"))
            for r in data.get("records", []):
                stem = r.get("item_id")
                group = r.get("group")
                if group in target_groups and stem and stem not in seen_ids:
                    if stem in wav_index:
                        items_to_process.append({
                            "item_id": stem,
                            "group": group,
                            "orig_prob": r.get("music_prob"),
                            "path": wav_index[stem]
                        })
                        seen_ids.add(stem)
        except Exception as e:
            logger.warning(f"Loi doc {af}: {e}")

    return items_to_process


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "processed_count": 0,
        "succeeded": 0,
        "failed": 0,
        "quarantined": 0,
        "completed_items": {},  # item_id -> {post_prob, status, time}
    }


def save_checkpoint(ckpt: dict):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_ckpt = CHECKPOINT_PATH.with_suffix(".tmp")
    temp_ckpt.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_ckpt.replace(CHECKPOINT_PATH)


def update_metadata_record(audio_path: Path, post_prob: float, is_quarantined: bool = False):
    """Cap nhat metadata.json cua thu muc tuong ung."""
    # Structure: WeekX/YYYY-MM-DD/audio/file.wav -> WeekX/YYYY-MM-DD/metadata.json
    day_dir = audio_path.parent.parent
    meta_file = day_dir / "metadata.json"
    if not meta_file.exists():
        return

    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        updated = False
        stem = audio_path.stem
        for rec in data:
            if rec.get("item_id") == stem:
                rec["vocal_separated"] = not is_quarantined
                rec["separation_engine"] = "demucs_htdemucs"
                rec["post_sep_music_prob"] = round(post_prob, 4)
                rec["post_sep_verified"] = not is_quarantined
                updated = True
                break
        if updated:
            meta_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Khong the cap nhat metadata {meta_file}: {e}")


def calculate_snr(audio_path: Path) -> float:
    """Tinh uoc luong Signal-to-Noise Ratio (dB) cua file WAV."""
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(str(audio_path))
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data - np.mean(data)
        rms = np.sqrt(np.mean(data**2))
        noise_floor = np.percentile(np.abs(data), 10) + 1e-9
        snr = 20 * np.log10((rms + 1e-9) / noise_floor)
        return round(float(snr), 2)
    except Exception:
        return 0.0


def run_test_evaluation(num_samples: int = 30):
    """
    Chay thu nghiem 30 file doi chung:
    - 15 file tu Nhóm 3B (BGM nang)
    - 15 file tu Nhóm 3A (BGM vua)
    - Copy before vao test_evaluation_30/before/
    - Tach Demucs
    - Copy after vao test_evaluation_30/after/
    - Tao bao cao Markdown so sanh.
    """
    eval_dir = PROJECT_ROOT / f"test_evaluation_{num_samples}"
    before_dir = eval_dir / "before"
    after_dir = eval_dir / "after"
    before_dir.mkdir(parents=True, exist_ok=True)
    after_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=======================================================", flush=True)
    print(f"[*] KHOI DONG CHE DO DANH GIA DOI CHUNG ({num_samples} FILE TEST)", flush=True)
    print(f"    - Thu muc Before: {before_dir}", flush=True)
    print(f"    - Thu muc After:  {after_dir}", flush=True)
    print(f"=======================================================\n", flush=True)

    items_3b = load_audit_files(phase="3b")
    items_3a = load_audit_files(phase="3a")

    half = num_samples // 2
    selected = items_3b[:half] + items_3a[:(num_samples - half)]
    print(f"[*] Da chon {len(selected)} file mau ({len(items_3b[:half])} 3B + {len(items_3a[:(num_samples-half)])} 3A)", flush=True)

    detector = MusicDetector()
    separator = VocalSeparator(model=DEFAULT_MODEL)

    eval_results = []
    t_start = time.time()

    for idx, item in enumerate(selected, start=1):
        orig_path = item["path"]
        item_id = item["item_id"]
        group = item["group"]

        # 1. Luu ban sao truoc khi tach (Before)
        before_file = before_dir / f"{item_id}.wav"
        shutil.copy2(orig_path, before_file)

        # Do chi so Before
        _, prob_before = detector.analyze(before_file)
        snr_before = calculate_snr(before_file)

        print(f"\n[{idx}/{len(selected)}] Dang tach {item_id} ({group}) | MusicProb goc: {prob_before:.2f} | SNR goc: {snr_before:.1f} dB...", flush=True)
        t_file0 = time.time()

        # 2. Thuc hien tach bang Demucs tren file goc
        sep_ok = separator.separate(orig_path)
        t_elapsed = time.time() - t_file0

        if sep_ok:
            # 3. Luu ban sao sau khi tach (After)
            after_file = after_dir / f"{item_id}.wav"
            shutil.copy2(orig_path, after_file)

            # Do chi so After (Post-Separation Gate)
            _, prob_after = detector.analyze(after_file)
            snr_after = calculate_snr(after_file)
            gate_pass = (prob_after <= 0.20)

            status = "PASSED_GATE" if gate_pass else "WARN_HIGH_BGM"
            print(f"    -> XONG ({t_elapsed:.1f}s) | MusicProb sau: {prob_after:.2f} (Giam {(prob_before-prob_after)*100:.1f}%) | SNR sau: {snr_after:.1f} dB (Tang +{snr_after-snr_before:.1f} dB) | Gate: {'[DAT]' if gate_pass else '[CANH BAO]'}", flush=True)

            eval_results.append({
                "item_id": item_id,
                "group": group,
                "duration_sec": round(t_elapsed, 1),
                "prob_before": round(prob_before, 4),
                "prob_after": round(prob_after, 4),
                "prob_reduction_pct": round((prob_before - prob_after) * 100, 1),
                "snr_before": snr_before,
                "snr_after": snr_after,
                "snr_gain_db": round(snr_after - snr_before, 2),
                "gate_status": status,
            })
            # Cap nhat metadata
            update_metadata_record(orig_path, prob_after, is_quarantined=not gate_pass)
        else:
            print(f"    -> THAT BAI khi tach Demucs!", flush=True)
            eval_results.append({
                "item_id": item_id,
                "group": group,
                "duration_sec": round(t_elapsed, 1),
                "prob_before": round(prob_before, 4),
                "prob_after": None,
                "prob_reduction_pct": 0,
                "snr_before": snr_before,
                "snr_after": None,
                "snr_gain_db": 0,
                "gate_status": "FAILED_SEPARATION",
            })

    total_time = time.time() - t_start

    # Xuat bao cao so sanh Markdown
    report_md = [
        f"# 📊 Báo Cáo Thử Nghiệm Đối Chứng Tách Nhạc BGM ({num_samples} File)",
        f"_Thời gian chạy: {time.strftime('%Y-%m-%d %H:%M:%S')} | Tổng thời gian: {total_time:.1f}s (Trung bình: {total_time/len(selected):.1f}s/file)_",
        "",
        "## 📂 Vị Trí Lưu Bản Sao Để Nghe Thử Trực Tiếp:",
        f"- **Bản sao Trước khi tách (Before):** `{before_dir}`",
        f"- **Bản sao Sau khi tách (After):**   `{after_dir}`",
        "",
        "---",
        "",
        "## 📈 Bảng So Sánh Chỉ Số Chi Tiết Trước vs Sau Khi Tách",
        "",
        "| STT | Audio Item ID | Nhóm Audit | Music Prob Trước | Music Prob Sau | Độ Giảm Nhạc | SNR Trước (dB) | SNR Sau (dB) | Độ Tăng SNR | Gate Status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    avg_prob_reduction = 0
    avg_snr_gain = 0
    passed_count = 0

    for idx, r in enumerate(eval_results, start=1):
        if r["gate_status"] == "PASSED_GATE":
            passed_count += 1
            avg_prob_reduction += r["prob_reduction_pct"]
            avg_snr_gain += r["snr_gain_db"]

        gate_str = "✅ ĐẠT" if r["gate_status"] == "PASSED_GATE" else "⚠️ CẢNH BÁO"
        report_md.append(
            f"| {idx} | `{r['item_id']}` | {r['group']} | {r['prob_before']:.2f} | "
            f"{r['prob_after'] if r['prob_after'] is not None else 'N/A'} | "
            f"-{r['prob_reduction_pct']}% | {r['snr_before']} dB | "
            f"{r['snr_after'] if r['snr_after'] is not None else 'N/A'} dB | "
            f"+{r['snr_gain_db']} dB | {gate_str} |"
        )

    if passed_count > 0:
        avg_prob_reduction /= passed_count
        avg_snr_gain /= passed_count

    report_md.extend([
        "",
        "---",
        "",
        "## 🎯 Tổng Kết Đánh Giá:",
        f"- **Tỷ lệ vượt qua Post-Separation Gate (`music_prob <= 0.20`):** {passed_count}/{len(selected)} ({passed_count/len(selected)*100:.1f}%)",
        f"- **Mức giảm xác suất nhạc trung bình:** -{avg_prob_reduction:.1f}%",
        f"- **Mức cải thiện chất lượng tín hiệu giọng nói (SNR gain trung bình):** +{avg_snr_gain:.2f} dB",
        f"- **Tốc độ xử lý trung bình:** {total_time/len(selected):.1f} giây/file",
        "",
        "### 💡 Hướng Dẫn Người Dùng Thẩm Định:",
        "1. Hãy mở các cặp file cùng tên trong 2 thư mục `test_evaluation_30/before` và `test_evaluation_30/after` để nghe đối chứng.",
        "2. Nếu chất lượng giọng nói trong trẻo, không bị méo tiếng và sạch nhạc nền → Bạn có thể ra lệnh tiến hành chạy các batch chính thức.",
    ])

    report_path = eval_dir / "comparison_report.md"
    report_path.write_text("\n".join(report_md), encoding="utf-8")
    print(f"\n[+] Da tao bao cao so sanh chi tiet tai: {report_path}", flush=True)


def run_batch_separation(phase: str = "all", batch_size: int = 500):
    """Chay tach nhac theo tung batch chia nho."""
    items = load_audit_files(phase=phase)
    ckpt = load_checkpoint()

    done_set = set(ckpt.get("completed_items", {}).keys())
    remaining = [it for it in items if it["item_id"] not in done_set]

    print(f"\n=======================================================", flush=True)
    print(f"[*] KHOI DONG TACH NHAC HANG LOAT (BATCH PROCESSING)", flush=True)
    print(f"    - Tong so file can tach theo Phase '{phase}': {len(items)}", flush=True)
    print(f"    - Da xu ly truoc do: {len(done_set)}", flush=True)
    print(f"    - Con lai: {len(remaining)}", flush=True)
    print(f"    - Kich thuoc batch lan nay: {min(batch_size, len(remaining))}", flush=True)
    print(f"=======================================================\n", flush=True)

    batch = remaining[:batch_size]
    if not batch:
        print("[*] Tat ca file trong phase nay da duoc xu ly hoan tat!", flush=True)
        return

    detector = MusicDetector()
    separator = VocalSeparator(model=DEFAULT_MODEL)

    t0 = time.time()
    for idx, it in enumerate(batch, start=1):
        item_id = it["item_id"]
        path = it["path"]
        group = it["group"]

        t_file0 = time.time()
        sep_ok = separator.separate(path)
        dur = time.time() - t_file0

        if sep_ok:
            _, post_prob = detector.analyze(path)
            passed = (post_prob <= 0.20)
            status = "SUCCESS" if passed else "QUARANTINE_POST_GATE"
            if passed:
                ckpt["succeeded"] += 1
            else:
                ckpt["quarantined"] += 1

            ckpt["completed_items"][item_id] = {
                "post_prob": round(post_prob, 4),
                "status": status,
                "duration_sec": round(dur, 1),
                "timestamp": time.time()
            }
            update_metadata_record(path, post_prob, is_quarantined=not passed)
        else:
            ckpt["failed"] += 1
            ckpt["completed_items"][item_id] = {
                "post_prob": None,
                "status": "FAILED",
                "duration_sec": round(dur, 1),
                "timestamp": time.time()
            }

        ckpt["processed_count"] += 1

        # Save checkpoint after every file
        save_checkpoint(ckpt)

        rate = (time.time() - t0) / idx
        eta = rate * (len(batch) - idx)
        print(f"  [{idx}/{len(batch)}] {item_id} | Status: {ckpt['completed_items'][item_id]['status']} | PostProb: {ckpt['completed_items'][item_id]['post_prob']} | Time: {dur:.1f}s | ETA Batch: {eta/60:.1f}m", flush=True)

    print(f"\n[+] Batch hoan tat! Tien trinh da duoc luu tai {CHECKPOINT_PATH}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Batch BGM Separator for ASR Dataset")
    parser.add_argument("--test-eval", type=int, default=None, help="Chay test danh gia doi chung N file (mac dinh 30)")
    parser.add_argument("--phase", type=str, default="all", choices=["3b", "3a", "2", "all"], help="Phase can xu ly (3b, 3a, 2, all)")
    parser.add_argument("--batch-size", type=int, default=500, help="So luong file moi dot chay")
    args = parser.parse_args()

    if args.test_eval is not None:
        run_test_evaluation(num_samples=args.test_eval)
    else:
        run_batch_separation(phase=args.phase, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
