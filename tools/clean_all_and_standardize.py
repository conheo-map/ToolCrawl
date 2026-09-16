"""
tools/clean_all_and_standardize.py — Dọn sạch 100% tệp rác, tệp thừa, tệp tạm debug
và chuyển đổi chuẩn hóa 2,277 audio về đúng 16,000 Hz, mono, pcm_s16le.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os
import json
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import soundfile as sf

BASE_DIR = Path(".")
ROOT_DRIVE_ID = "16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw"

# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 1: CHUẨN HÓA 2,277 TỆP AUDIO VỀ ĐÚNG 16,000 Hz MONO PCM_S16LE
# ─────────────────────────────────────────────────────────────────────────────
def step1_standardize_audio_spec():
    print("=" * 85)
    print("  BƯỚC 1: CHUẨN HÓA 100% AUDIO VỀ WAV 16,000 Hz MONO PCM_S16LE")
    print("=" * 85)
    t0 = time.time()

    to_convert = []
    for mf in BASE_DIR.glob("Week*/*/metadata.json"):
        audio_dir = mf.parent / "audio"
        if not audio_dir.exists(): continue
        for w in audio_dir.glob("*.wav"):
            try:
                info = sf.info(str(w))
                if info.samplerate != 16000 or info.channels != 1 or info.subtype != "PCM_16":
                    to_convert.append(w)
            except Exception:
                pass

    print(f"[*] Tìm thấy {len(to_convert):,} tệp cần chuẩn hóa về 16kHz mono PCM_S16LE...")

    def convert_one(wav_path):
        tmp_out = wav_path.with_suffix(".tmp.wav")
        cmd = [
            "ffmpeg", "-y", "-i", str(wav_path),
            "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            str(tmp_out)
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        if res.returncode == 0 and tmp_out.exists():
            tmp_out.replace(wav_path)
            return True
        else:
            if tmp_out.exists(): tmp_out.unlink()
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(convert_one, to_convert))

    success = sum(1 for r in results if r)
    print(f"[+] Đã chuyển đổi thành công {success:,} / {len(to_convert):,} tệp ({time.time()-t0:.1f}s)!\n")


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 2: XÓA CÁC FILE MỒ CÔI (FILE RÁC CÒN SÓT TRÊN ĐĨA)
# ─────────────────────────────────────────────────────────────────────────────
def step2_delete_orphaned_audio():
    print("=" * 85)
    print("  BƯỚC 2: XÓA CÁC TỆP AUDIO MỒ CÔI (RÁC ĐÃ GỠ KHỎI METADATA NHƯNG CÒN TRÊN ĐĨA)")
    print("=" * 85)

    all_meta_ids = set()
    for mf in BASE_DIR.glob("Week*/*/metadata.json"):
        recs = json.loads(mf.read_text(encoding="utf-8"))
        for r in recs:
            all_meta_ids.add(r["item_id"])

    deleted_orphans = 0
    for mf in BASE_DIR.glob("Week*/*/metadata.json"):
        audio_dir = mf.parent / "audio"
        if not audio_dir.exists(): continue
        for w in audio_dir.glob("*.wav"):
            if w.stem not in all_meta_ids:
                try:
                    w.unlink()
                    deleted_orphans += 1
                except Exception:
                    pass

    print(f"[+] Đã xóa sạch {deleted_orphans} tệp audio mồ côi khỏi đĩa cứng!\n")


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 3: DỌN SẠCH CÁC TỆP DEBUG, TỆP TEST, SCRIPT THỪA KHÔNG DÙNG
# ─────────────────────────────────────────────────────────────────────────────
def step3_cleanup_unused_files():
    print("=" * 85)
    print("  BƯỚC 3: DỌN SẠCH CÁC TỆP TẠM, TỆP TEST, DUMP LOG & SCRIPT DEBUG CŨ")
    print("=" * 85)

    files_to_remove = [
        # Tệp test tạm thời
        BASE_DIR / "test_7655990941505113365.mp4",
        BASE_DIR / "test_7655990941505113365.wav",
        BASE_DIR / "ab_test_speech_master.py",
        BASE_DIR / "finish_sync_today.py",
        BASE_DIR / "fix_sync_25.py",
        BASE_DIR / "run_complete_sync.py",
        BASE_DIR / "audit_summary.json",
        
        # Script debug / tạm thời trong tools/
        BASE_DIR / "tools/extract_bna_samples.py",
        BASE_DIR / "tools/audit_bao_nghe_an.py",
        BASE_DIR / "tools/analyze_asr_exclusions.py",
        BASE_DIR / "tools/detect_bad_files.py",
        BASE_DIR / "tools/extract_all_bad_files.py",
        BASE_DIR / "tools/drive_deep_audit.py",
        BASE_DIR / "tools/calibrate_durations.py",
        BASE_DIR / "tools/verify_actual_hours.py",
        BASE_DIR / "tools/final_dataset_evaluation.py",
        BASE_DIR / "tools/reconcile_drive.py",
        BASE_DIR / "tools/force_push_metadata_to_drive.py",
        BASE_DIR / "tools/audit_and_cleanse_topics.py",
        BASE_DIR / "tools/master_full_audit.py",
        BASE_DIR / "tools/master_region_tagger_and_summary.py",
        BASE_DIR / "tools/sync_and_recalculate_all.py",
        BASE_DIR / "tools/turbo_cleanse_and_tag_regions.py"
    ]

    dirs_to_remove = [
        BASE_DIR / "tools/bad_files_report",
        BASE_DIR / "tools/evaluation_reports",
        BASE_DIR / "tools/master_audit_results",
        BASE_DIR / "tools/__pycache__",
        BASE_DIR / "utils/__pycache__",
        BASE_DIR / "storage/__pycache__",
        BASE_DIR / "processors/__pycache__",
        BASE_DIR / "crawlers/__pycache__"
    ]

    del_f_count = 0
    for f in files_to_remove:
        if f.exists():
            try:
                f.unlink()
                del_f_count += 1
            except Exception:
                pass

    del_d_count = 0
    for d in dirs_to_remove:
        if d.exists():
            try:
                shutil.rmtree(d, ignore_errors=True)
                del_d_count += 1
            except Exception:
                pass

    print(f"[+] Đã xóa {del_f_count} tệp debug/test thừa.")
    print(f"[+] Đã xóa {del_d_count} thư mục tạm/cache không cần thiết.\n")


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 4: ĐỒNG BỘ CÁC TỆP 16KHZ ĐÃ CHUẨN HÓA LÊN GOOGLE DRIVE
# ─────────────────────────────────────────────────────────────────────────────
def step4_sync_to_drive():
    print("=" * 85)
    print("  BƯỚC 4: ĐỒNG BỘ 100% CÁC AUDIO ĐÃ CHUẨN HÓA 16KHZ LÊN GOOGLE DRIVE")
    print("=" * 85)
    t0 = time.time()

    cmd = [
        "rclone", "copy", "Week2", f"gdrive,root_folder_id={ROOT_DRIVE_ID}:Week2",
        "--transfers", "12", "--checkers", "16", "--fast-list", "--update"
    ]
    res = subprocess.run(cmd)
    print(f"[+] Đồng bộ Week2: mã {res.returncode}")

    cmd3 = [
        "rclone", "copy", "Week3", f"gdrive,root_folder_id={ROOT_DRIVE_ID}:Week3",
        "--transfers", "12", "--checkers", "16", "--fast-list", "--update"
    ]
    res3 = subprocess.run(cmd3)
    print(f"[+] Đồng bộ Week3: mã {res3.returncode}")
    print(f"[+] Hoàn tất đồng bộ trong {time.time()-t0:.1f}s\n")


if __name__ == "__main__":
    step1_standardize_audio_spec()
    step2_delete_orphaned_audio()
    step3_cleanup_unused_files()
    step4_sync_to_drive()
