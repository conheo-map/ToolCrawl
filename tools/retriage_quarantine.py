"""
tools/retriage_quarantine.py — Tái phân loại 2,327 files trong thư mục Quarantine.

[SPRINT 3.2]
Quét toàn bộ các file trong quarantine (Week1 - Week4), chạy kiểm định bằng:
  1. Multi-window MusicDetector (HPSS + Continuous music_prob)
  2. SyntheticSpeechDetector (F0 Jitter, Spectral Flux, Vocoder Phase)

Phân loại các mẫu audio theo 4 nhóm hành động:
  - REJECT (Loại bỏ hoàn toàn): music_prob >= 0.70 hoặc TTS synthetic_prob > 0.70
  - REMEDIATION (Tách nguồn): 0.30 <= music_prob < 0.70 (Khôi phục bằng Demucs AI)
  - AUGMENTATION (Giữ làm nhiễu): 0.15 <= music_prob < 0.30 (BGM nhẹ + giọng nói rõ)
  - FALSE_POSITIVE (Phục hồi sạch): music_prob < 0.15 (Chuyển ngược lại về audio/)
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
from pathlib import Path
from tqdm import tqdm

from processors.music_detector import MusicDetector
from processors.synthetic_speech_detector import SyntheticSpeechDetector
from config import (
    MUSIC_PROB_REJECT,
    MUSIC_PROB_SEPARATE,
    MUSIC_PROB_AUGMENT,
    SSD_PROB_REJECT,
)


def retriage(quarantine_dirs: list[Path], output_report: Path) -> dict:
    music_detector = MusicDetector()
    ssd = SyntheticSpeechDetector()

    all_files: list[Path] = []
    for q_dir in quarantine_dirs:
        if q_dir.exists():
            all_files.extend(list(q_dir.glob("*.wav")))

    print(f"[*] Tìm thấy tổng cộng {len(all_files)} files trong các thư mục quarantine.")

    results = {
        "summary": {
            "total_files": len(all_files),
            "reject_count": 0,
            "remediation_count": 0,
            "augmentation_count": 0,
            "false_positive_count": 0,
            "synthetic_count": 0,
        },
        "records": []
    }

    for wav_file in tqdm(all_files, desc="Retriaging quarantine"):
        is_music, music_prob = music_detector.analyze(wav_file)
        synth_prob, synth_tag = ssd.analyze(wav_file)

        # Phân loại
        if synth_prob > SSD_PROB_REJECT:
            category = "REJECT_SYNTHETIC"
            action = "reject"
            results["summary"]["synthetic_count"] += 1
            results["summary"]["reject_count"] += 1
        elif music_prob >= MUSIC_PROB_REJECT:
            category = "REJECT_SEVERE_BGM"
            action = "reject"
            results["summary"]["reject_count"] += 1
        elif music_prob >= MUSIC_PROB_SEPARATE:
            category = "REMEDIATION_DEMUCS"
            action = "remediate"
            results["summary"]["remediation_count"] += 1
        elif music_prob >= MUSIC_PROB_AUGMENT:
            category = "AUGMENTATION_BGM"
            action = "augment"
            results["summary"]["augmentation_count"] += 1
        else:
            category = "FALSE_POSITIVE_CLEAN"
            action = "restore"
            results["summary"]["false_positive_count"] += 1

        results["records"].append({
            "file": str(wav_file),
            "filename": wav_file.name,
            "music_prob": round(music_prob, 4),
            "synthetic_prob": round(synth_prob, 4),
            "synth_tag": synth_tag,
            "category": category,
            "recommended_action": action,
        })

    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 50)
    print("KẾT QUẢ RETRIAGE QUARANTINE")
    print("=" * 50)
    print(f"Tổng số files kiểm tra:       {results['summary']['total_files']}")
    print(f"1. REJECT (BGM nặng / TTS):    {results['summary']['reject_count']} (trong đó {results['summary']['synthetic_count']} TTS)")
    print(f"2. REMEDIATION (Có thể tách):  {results['summary']['remediation_count']}")
    print(f"3. AUGMENTATION (BGM làm nền): {results['summary']['augmentation_count']}")
    print(f"4. FALSE POSITIVE (Sạch):      {results['summary']['false_positive_count']}")
    print(f"\nBáo cáo chi tiết đã lưu tại: {output_report}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Retriage quarantined audio files across all weeks")
    parser.add_argument("--weeks-root", type=str, default=".", help="Root directory containing Week1, Week2, ...")
    parser.add_argument("--output", type=str, default="local_research/quarantine_retriage_report.json")
    args = parser.parse_args()

    root = Path(args.weeks_root)
    quarantine_dirs = list(root.glob("Week*/*/quarantine"))
    retriage(quarantine_dirs, Path(args.output))


if __name__ == "__main__":
    main()
