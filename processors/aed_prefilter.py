"""
processors/aed_prefilter.py — Stage 0 Audio Event Detector (YAMNet / Lightweight AED).

[UPGRADE 2.1]
Chạy kiểm định sơ bộ nhanh (5-10s đầu) để tính xác suất âm nhạc (music_prob)
và tiếng nói (speech_prob).
Nếu video là 100% music/clip không lời, có thể loại bỏ sớm trước các bước xử lý nặng.

Hỗ trợ:
  1. TFLite / YAMNet model (nếu có tflite-runtime / tensorflow)
  2. Fast Spectral Flux & Harmonicity filter fallback (chạy cực nhanh bằng librosa / numpy)
"""

from __future__ import annotations

from pathlib import Path
from utils.logger import get_logger
from config import (
    MUSIC_PROB_REJECT,
    MUSIC_PROB_SEPARATE,
)

logger = get_logger("aed_prefilter")


class AudioEventPreFilter:
    """
    Stage 0 Pre-filter: Phát hiện nhanh sự kiện âm thanh (Music vs Speech).
    """

    def __init__(self, sample_duration_sec: float = 10.0) -> None:
        self.sample_duration = sample_duration_sec
        self._yamnet_model = None
        self._init_engine()

    def _init_engine(self) -> None:
        """Thử load YAMNet TFLite nếu có sẵn, nếu không dùng Fast Spectral Engine."""
        try:
            # Kiểm tra tflite-runtime hoặc tensorflow
            import tflite_runtime.interpreter as tflite
            model_path = Path("models/yamnet.tflite")
            if model_path.exists():
                self._interpreter = tflite.Interpreter(model_path=str(model_path))
                self._interpreter.allocate_tensors()
                self._yamnet_model = "tflite"
                logger.info("AEDPreFilter: YAMNet TFLite engine ACTIVE")
                return
        except Exception:
            pass

        logger.info("AEDPreFilter: Fast Spectral Audio Event Detector ACTIVE (CPU optimized)")

    def predict_events(self, audio_path: Path) -> dict:
        """
        Phân tích 5-10s đầu của file audio.
        Trả về dict:
          {
            "music_prob": float (0.0 - 1.0),
            "speech_prob": float (0.0 - 1.0),
            "is_pure_music": bool,
            "engine": str
          }
        """
        if not audio_path.exists():
            return {"music_prob": 0.0, "speech_prob": 0.0, "is_pure_music": False, "engine": "none"}

        try:
            import librosa
            import numpy as np

            # Load nhanh sample_duration giây đầu với 16kHz mono
            y, sr = librosa.load(
                str(audio_path),
                sr=16000,
                mono=True,
                duration=self.sample_duration,
            )

            if len(y) < sr * 1.5:
                return {"music_prob": 0.0, "speech_prob": 1.0, "is_pure_music": False, "engine": "fallback"}

            # 1. Harmonic Energy Ratio
            y_harm, y_perc = librosa.effects.hpss(y, margin=(1.0, 4.0))
            harm_e = float(np.sum(y_harm ** 2))
            perc_e = float(np.sum(y_perc ** 2))
            total_e = float(np.sum(y ** 2)) + 1e-9

            harm_ratio = harm_e / total_e

            # 2. Spectral Flatness & Contrast
            flatness = float(np.mean(librosa.feature.spectral_flatness(y=y)))
            contrast = float(np.mean(librosa.feature.spectral_contrast(y=y, sr=sr)))

            # 3. Zero-Crossing Rate (ZCR)
            zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))

            # Heuristics:
            # Nhạc: Harm ratio cao, Contrast cao, Flatness thấp
            music_score = (
                0.45 * min(1.0, max(0.0, (harm_ratio - 0.20) / 0.35)) +
                0.35 * min(1.0, max(0.0, (contrast - 12.0) / 12.0)) +
                0.20 * min(1.0, max(0.0, (0.02 - flatness) / 0.02))
            )
            music_prob = float(np.clip(music_score, 0.0, 1.0))

            # Giọng nói: ZCR trong khoảng 0.04 - 0.18, flatness trung bình
            speech_zcr_score = 1.0 - min(1.0, abs(zcr - 0.08) / 0.08)
            speech_prob = float(np.clip(0.6 * speech_zcr_score + 0.4 * (1.0 - music_prob), 0.0, 1.0))

            is_pure_music = (music_prob > MUSIC_PROB_REJECT) and (speech_prob < 0.25)

            return {
                "music_prob": round(music_prob, 4),
                "speech_prob": round(speech_prob, 4),
                "is_pure_music": is_pure_music,
                "engine": "fast_spectral",
            }

        except Exception as exc:
            logger.warning(f"[AEDPreFilter] Error analyzing {audio_path.name}: {exc}")
            return {"music_prob": 0.0, "speech_prob": 1.0, "is_pure_music": False, "engine": "error"}
