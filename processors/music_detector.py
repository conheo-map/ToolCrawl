"""
processors/music_detector.py — Phát hiện nhạc nền trong audio.

Hai tầng:
  1. Metadata heuristic: nhanh, không tốn CPU.
  2. Signal heuristic: dùng librosa phân tích spectral flatness.
"""

import shutil
from pathlib import Path
from utils.logger import get_logger
from config import (
    MUSIC_FILTER_ENABLED,
    MUSIC_FLATNESS_THRESHOLD,
    MUSIC_ANALYSIS_SAMPLE_SEC,
    MUSIC_QUARANTINE_INSTEAD_OF_DELETE,
    QUARANTINE_DIR,
)

import config as cfg

logger = get_logger("music_detector")


class MusicDetector:
    """
    Phát hiện audio có nhạc nền và quyết định giữ/quarantine/xóa.
    """

    def __init__(self, enabled: bool | None = None) -> None:
        self._has_librosa = False
        self._enabled = enabled if enabled is not None else cfg.MUSIC_FILTER_ENABLED
        if not self._enabled:
            logger.info("Music detection disabled")
            return

        try:
            import librosa  # noqa: F401
            self._has_librosa = True
            logger.info("Music detector initialized with librosa signal analysis")
        except ImportError:
            logger.warning(
                "librosa not installed — using metadata heuristic only. "
                "Install with: pip install librosa"
            )

    def is_music(self, audio_path: Path, metadata: dict | None = None) -> bool:
        """
        Trả về True nếu audio có nhạc nền (nên reject).
        Ưu tiên metadata heuristic trước, sau đó mới dùng signal analysis.
        """
        if not self._enabled or not cfg.MUSIC_FILTER_ENABLED:
            return False

        # --- Tầng 1: Metadata heuristic ---
        if metadata:
            result = self._check_metadata(metadata)
            if result is True:
                logger.info(
                    f"[metadata] Music detected (metadata flag): {audio_path.name}"
                )
                return True
            if result is False:
                # Metadata rõ ràng là clean — skip signal analysis
                return False
            # result is None: không chắc -> dùng signal analysis

        # --- Tầng 2: Signal heuristic ---
        if self._has_librosa and audio_path.exists():
            return self._check_signal(audio_path)

        return False

    def process(self, audio_path: Path, metadata: dict | None = None) -> bool:
        """
        Kiểm tra và xử lý: quarantine hoặc xóa nếu có nhạc.
        Trả về True nếu audio bị reject.
        """
        if not self.is_music(audio_path, metadata):
            return False

        if MUSIC_QUARANTINE_INSTEAD_OF_DELETE:
            QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
            dest = QUARANTINE_DIR / audio_path.name
            shutil.move(str(audio_path), dest)
            logger.warning(f"Quarantined (music detected): {audio_path.name}")
        else:
            audio_path.unlink(missing_ok=True)
            logger.warning(f"Deleted (music detected): {audio_path.name}")

        return True

    # ─────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────

    def _check_metadata(self, metadata: dict) -> bool | None:
        """
        Kiểm tra metadata từ yt-dlp info_dict.
        Trả về:
          True  — rõ ràng có nhạc
          False — rõ ràng không có nhạc (original audio)
          None  — không chắc, cần signal analysis
        """
        platform = metadata.get("platform", "")

        if platform == "tiktok":
            platform_meta = metadata.get("platform_meta", {})
            music_is_original = platform_meta.get("music_is_original")

            if music_is_original is False:
                # Original audio = False → có thể có nhạc nền
                track = metadata.get("_track", "")
                if track and track.lower() not in (
                    "", "original sound", "âm thanh gốc", "tiếng động gốc"
                ):
                    return True  # Nhạc nền có tên rõ ràng
                return None  # Không chắc

            if music_is_original is True:
                return False  # Original sound → không có nhạc nền

        if platform == "facebook":
            # Facebook không có signal rõ trong metadata
            return None

        return None

    def _check_signal(self, audio_path: Path) -> bool:
        """
        Phân tích spectral flatness bằng librosa.
        Spectral flatness thấp → năng lượng tập trung → dấu hiệu nhạc.
        Spectral flatness cao → phân bố đều tần số → dấu hiệu speech.
        """
        import librosa
        import numpy as np

        try:
            # Load chỉ MUSIC_ANALYSIS_SAMPLE_SEC giây đầu để tiết kiệm CPU
            y, sr = librosa.load(
                str(audio_path),
                sr=None,
                duration=MUSIC_ANALYSIS_SAMPLE_SEC,
                mono=True,
            )

            if len(y) < sr * 2:  # Quá ngắn để phân tích
                return False

            # Tính spectral flatness theo frame
            flatness = librosa.feature.spectral_flatness(
                y=y, n_fft=2048, hop_length=512
            )
            flatness_mean = float(np.mean(flatness))

            is_music = flatness_mean < MUSIC_FLATNESS_THRESHOLD

            logger.debug(
                f"Signal analysis {audio_path.name}: "
                f"flatness={flatness_mean:.4f} "
                f"threshold={MUSIC_FLATNESS_THRESHOLD} "
                f"-> {'MUSIC' if is_music else 'SPEECH'}"
            )
            return is_music

        except Exception as exc:
            logger.warning(f"Signal analysis failed for {audio_path.name}: {exc}")
            return False
