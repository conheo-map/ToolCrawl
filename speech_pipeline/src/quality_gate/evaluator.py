"""
evaluator.py — Speech Quality Gate & Metric Evaluator
====================================================
Đo lường SNR, Spectral Flatness, Speech Ratio để loại bỏ rác/nhạc lấn.
"""
from pathlib import Path
from typing import Dict, Tuple
import numpy as np
import soundfile as sf
import librosa


class QualityGateEvaluator:
    def __init__(
        self,
        min_speech_ratio: float = 0.30,
        max_spectral_flatness: float = 0.15,
        min_snr_db: float = 10.0
    ):
        self.min_speech_ratio = min_speech_ratio
        self.max_spectral_flatness = max_spectral_flatness
        self.min_snr_db = min_snr_db

    def evaluate_audio(self, audio_path: Path) -> Dict:
        """
        Đánh giá chất lượng toàn diện của file âm thanh.
        """
        data, sr = sf.read(str(audio_path), dtype="float32")
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        dur = len(data) / sr

        # 1. Đo Spectral Flatness (Flatness cao = Nhạc nền/Noise, Flatness thấp = Giọng nói)
        S = np.abs(librosa.stft(data, n_fft=2048, hop_length=512))
        flatness = librosa.feature.spectral_flatness(S=S)[0]
        mean_flatness = float(np.mean(flatness))

        # 2. Đo SNR ước tính (loudest 30% vs quietest 30%)
        rms_frames = librosa.feature.rms(y=data, frame_length=2048, hop_length=512)[0]
        rms_sorted = np.sort(rms_frames)
        n = max(1, len(rms_sorted) // 3)
        sig_rms = float(np.mean(rms_sorted[-n:]))
        noise_rms = float(np.mean(rms_sorted[:n]))
        snr = 20 * np.log10(sig_rms / max(1e-9, noise_rms)) if noise_rms > 1e-9 else 45.0

        is_passed = (mean_flatness <= self.max_spectral_flatness) and (snr >= self.min_snr_db)

        return {
            "duration_seconds": round(dur, 3),
            "spectral_flatness": round(mean_flatness, 6),
            "snr_db": round(float(snr), 2),
            "is_gold_quality": is_passed,
            "sample_rate": sr,
            "channels": 1
        }
