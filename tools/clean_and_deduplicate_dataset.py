import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os
import shutil
import hashlib
import time
import json
from pathlib import Path
import numpy as np
import soundfile as sf

def compute_audio_hash(data: np.ndarray, sr: int) -> str:
    """Tinh hash tren chuoi mau waveform chuan hoa."""
    # Lam tron 3 chu so thap phan de bat trung lap waveform
    quantized = np.round(data * 1000).astype(np.int16)
    return hashlib.md5(quantized.tobytes()).hexdigest()

def compute_speech_metrics(data: np.ndarray, sr: int):
    """
    Tinh toan chi so nang luong va ty le giong noi (VAD/Energy):
    - RMS energy
    - Zero Crossing Rate
    - Speech activity ratio
    """
    if len(data) == 0:
        return 0.0, 0.0, 0.0

    # 1. RMS Energy
    rms = float(np.sqrt(np.mean(data ** 2)))

    # 2. Frame-based voice energy (frame 30ms = 480 samples o 16kHz)
    frame_len = int(sr * 0.03)
    n_frames = len(data) // frame_len
    if n_frames == 0:
        return rms, 0.0, 0.0

    frames = data[:n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))

    # Nguong phat hien tieng noi (speech threshold)
    speech_thresh = max(0.008, np.percentile(frame_rms, 20) * 1.8)
    speech_frames = np.sum(frame_rms > speech_thresh)
    speech_ratio = float(speech_frames / n_frames)
    speech_duration = speech_ratio * (len(data) / sr)

    return rms, speech_ratio, speech_duration

def main():
    root = Path(r"c:\HocC\SaydiTool\dataset_2026-09-17")
    audio_dir = root / "audio"
    quarantine_dir = root / "quarantine"
    quarantine_dup_dir = quarantine_dir / "duplicate_audio"
    quarantine_silent_dir = quarantine_dir / "silent_or_low_voice"
    
    quarantine_dup_dir.mkdir(parents=True, exist_ok=True)
    quarantine_silent_dir.mkdir(parents=True, exist_ok=True)

    wav_files = sorted(list(audio_dir.glob("*.wav")))
    total_files = len(wav_files)

    print("=" * 80)
    print(f"🧹 BẮT ĐẦU QUÉT & LỌC CHẤT LƯỢNG DATASET 2026-09-17")
    print(f"Tổng số file cần quét: {total_files:,} files")
    print("=" * 80 + "\n")

    seen_audio_hashes = {}  # hash -> first file path
    seen_fingerprints = {}  # (dur_round, energy_round) -> file_path
    
    clean_items = []
    removed_duplicates = []
    removed_low_voice = []

    t0 = time.time()

    for idx, wav_path in enumerate(wav_files, 1):
        try:
            data, sr = sf.read(str(wav_path), dtype="float32")
            dur = len(data) / sr
            item_id = wav_path.stem

            # ── 1. KIỂM TRA IM LẶNG / ÍT GIỌNG NÓI ──
            rms, speech_ratio, speech_dur = compute_speech_metrics(data, sr)

            if rms < 0.004 or speech_dur < 1.8 or speech_ratio < 0.15:
                # File qua be, im lang hoac khong chua giong noi
                reason = f"RMS={rms:.4f}, SpeechDur={speech_dur:.1f}s ({speech_ratio*100:.0f}%)"
                dst_q = quarantine_silent_dir / wav_path.name
                shutil.move(str(wav_path), str(dst_q))
                removed_low_voice.append({"item_id": item_id, "reason": reason, "path": str(dst_q)})
                continue

            # ── 2. KIỂM TRA TRÙNG LẶP AUDIO (DUPLICATE) ──
            a_hash = compute_audio_hash(data, sr)
            # Perceptual fingerprint: thoi luong (lam tron 0.1s) + RMS (lam tron 3 chu so)
            fp = (round(dur, 1), round(rms, 3))

            if a_hash in seen_audio_hashes:
                orig_file = seen_audio_hashes[a_hash]
                dst_q = quarantine_dup_dir / wav_path.name
                shutil.move(str(wav_path), str(dst_q))
                removed_duplicates.append({"item_id": item_id, "orig": orig_file.name, "path": str(dst_q), "type": "exact_hash"})
                continue
            
            seen_audio_hashes[a_hash] = wav_path

            # File dat chuan 100%
            clean_items.append({
                "item_id": item_id,
                "audio_file": f"audio/{wav_path.name}",
                "duration_seconds": round(dur, 3),
                "rms_energy": round(rms, 4),
                "speech_ratio": round(speech_ratio, 2),
                "sample_rate": sr,
                "channels": 1,
                "format": "wav_pcm_s16le",
            })

        except Exception as exc:
            print(f"[-] Loi doc {wav_path.name}: {exc}")

        if idx % 500 == 0 or idx == total_files:
            print(f"  - Đã quét: {idx:,}/{total_files:,} files (Giữ lại: {len(clean_items):,} | Trùng: {len(removed_duplicates)} | Ít giọng: {len(removed_low_voice)})...")

    # ── CẬP NHẬT METADATA & SUMMARY ──
    tot_dur = sum(it["duration_seconds"] for it in clean_items)
    tot_hours = round(tot_dur / 3600.0, 2)

    meta_file = root / "metadata.json"
    meta_file.write_text(json.dumps(clean_items, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_data = {
        "dataset_name": root.name,
        "crawl_date": "2026-09-17",
        "total_initial_files": total_files,
        "clean_files_delivered": len(clean_items),
        "total_hours": tot_hours,
        "quarantined_duplicates": len(removed_duplicates),
        "quarantined_low_voice": len(removed_low_voice),
        "qc_passed_rate": f"{len(clean_items)/total_files*100:.1f}%",
        "audio_spec": {
            "sample_rate": 16000,
            "channels": 1,
            "format": "wav_pcm_s16le",
            "vocal_isolated": "demucs_htdemucs",
            "vad_segmented": "silero_vad",
        }
    }
    sum_file = root / "summary.json"
    sum_file.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")

    report_file = root / "qc_cleaning_report.json"
    report_file.write_text(json.dumps({
        "summary": summary_data,
        "duplicates_removed": removed_duplicates,
        "low_voice_removed": removed_low_voice,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    t_elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print("🎉 HOÀN TẤT QUÉT & LỌC SẠCH DỮ LIỆU TRONG {:.1f} GIÂY!".format(t_elapsed))
    print("=" * 80)
    print(f"  - Tổng số file ban đầu: {total_files:,} files")
    print(f"  - File TRÙNG LẶP (Duplicate) đã loại: {len(removed_duplicates):,} files")
    print(f"  - File IM LẶNG / ÍT GIỌNG NÓI đã loại: {len(removed_low_voice):,} files")
    print(f"  - File SẠCH CHUẨN ASR GIỮ LẠI: {len(clean_items):,} files (Tỉ lệ đạt: {len(clean_items)/total_files*100:.1f}%)")
    print(f"  - Tổng thời lượng giọng nói sạch: {tot_hours:.2f} giờ")
    print(f"  - Thư mục cách ly file lỗi: {quarantine_dir}")
    print(f"  - Báo cáo QC chi tiết: {report_file}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
