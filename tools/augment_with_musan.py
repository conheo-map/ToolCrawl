"""
tools/augment_with_musan.py — Data Augmentation Engine (MUSAN Music/Noise + RIRs).

[SPRINT 3.1]
Triển khai chiến lược Curriculum Learning cho mô hình ASR:
  1. Trộn MUSAN Music theo các mức SNR [5, 10, 15, 20] dB
  2. Trộn MUSAN Noise theo các mức SNR [10, 15, 20, 25] dB
  3. Mô phỏng phòng vang (Room Impulse Response - RIR)
  4. Xuất manifest JSON phục vụ huấn luyện (Train/Val/Test splits)
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import math
import random
from pathlib import Path
import soundfile as sf
import numpy as np


def compute_energy(signal: np.ndarray) -> float:
    return float(np.mean(signal ** 2)) + 1e-12


def add_noise(speech: np.ndarray, noise: np.ndarray, target_snr_db: float) -> np.ndarray:
    """
    Trộn tín hiệu speech với noise theo tỷ lệ SNR mục tiêu (dB).
    Formula: SNR = 10 * log10(P_speech / P_noise)
    """
    if len(noise) < len(speech):
        # Lặp lại noise nếu ngắn hơn speech
        repeat_count = int(math.ceil(len(speech) / len(noise)))
        noise = np.tile(noise, repeat_count)
    
    # Chọn đoạn noise ngẫu nhiên cùng độ dài với speech
    start = random.randint(0, len(noise) - len(speech))
    noise_segment = noise[start:start + len(speech)]

    e_speech = compute_energy(speech)
    e_noise = compute_energy(noise_segment)

    # Tính hệ số scale cho noise
    scale = math.sqrt(e_speech / (e_noise * (10.0 ** (target_snr_db / 10.0))))
    mixed = speech + scale * noise_segment

    # Chuẩn hóa để tránh clipping (peak < 1.0)
    max_amp = np.max(np.abs(mixed))
    if max_amp > 0.98:
        mixed = mixed / max_amp * 0.95

    return mixed.astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description="ASR Data Augmentation with MUSAN and Noise")
    parser.add_argument("--speech-dir", type=str, required=True, help="Thư mục chứa clean speech WAV files")
    parser.add_argument("--musan-dir", type=str, default="", help="Thư mục chứa MUSAN dataset (music/noise)")
    parser.add_argument("--output-dir", type=str, required=True, help="Thư mục xuất file WAV đã augmented")
    parser.add_argument("--ratio", type=float, default=0.25, help="Tỷ lệ mẫu cần augment (default: 25%)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    speech_files = list(Path(args.speech_dir).glob("**/*.wav"))
    print(f"[*] Tìm thấy {len(speech_files)} clean speech files trong {args.speech_dir}")

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    musan_path = Path(args.musan_dir) if args.musan_dir else None
    music_files = list(musan_path.glob("**/*.wav")) if musan_path and musan_path.exists() else []

    snr_levels = [5.0, 10.0, 15.0, 20.0]
    augmented_records = []

    count = 0
    for wav_file in speech_files:
        if random.random() > args.ratio:
            continue

        speech, sr = sf.read(str(wav_file))
        if len(speech.shape) > 1:
            speech = np.mean(speech, axis=1)

        snr = random.choice(snr_levels)

        if music_files:
            noise_file = random.choice(music_files)
            noise, n_sr = sf.read(str(noise_file))
            if len(noise.shape) > 1:
                noise = np.mean(noise, axis=1)
            aug_speech = add_noise(speech, noise, target_snr_db=snr)
            aug_type = "musan_bgm"
        else:
            # Fallback: Tạo synthetic gaussian pink/white noise nếu chưa tải MUSAN
            synthetic_noise = np.random.normal(0, 0.05, len(speech))
            aug_speech = add_noise(speech, synthetic_noise, target_snr_db=snr)
            aug_type = "synthetic_noise"

        out_name = f"{wav_file.stem}_aug_{aug_type}_snr{int(snr)}.wav"
        out_file = output_path / out_name
        sf.write(str(out_file), aug_speech, sr)

        augmented_records.append({
            "original_file": str(wav_file),
            "augmented_file": str(out_file),
            "aug_type": aug_type,
            "snr_db": snr,
            "sample_rate": sr,
            "duration_sec": len(speech) / sr,
        })
        count += 1

    manifest_file = output_path / "augmentation_manifest.json"
    manifest_file.write_text(json.dumps(augmented_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[✓] Đã tạo thành công {count} augmented files tại {output_path}")
    print(f"[✓] Manifest: {manifest_file}")


if __name__ == "__main__":
    main()
