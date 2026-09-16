"""
processors/music_detector.py — Phát hiện nhạc nền trong audio.

Hai tầng:
  1. Metadata heuristic: nhanh, không tốn CPU.
  2. Signal heuristic: dùng librosa phân tích HPSS đa cửa sổ.

[UPGRADE 2.2]
  - _check_signal() → _check_signal_multiwindow(): phân tích 3 cửa sổ (đầu/giữa/cuối)
    thay vì chỉ 30s đầu, trả về music_prob float 0.0-1.0 thay vì binary.
  - process() trả về tuple (status: str, music_prob: float).
  - Nguong harm_ratio ha 0.60 -> 0.45; contrast 22.0 -> 20.0.
  - HPSS margin=(1.0, 5.0) de khong nham phu am xat tieng Viet la harmonic.
"""

import shutil
from pathlib import Path
from utils.logger import get_logger
from config import (
    MUSIC_FILTER_ENABLED,
    MUSIC_ANALYSIS_SAMPLE_SEC,
    MUSIC_QUARANTINE_INSTEAD_OF_DELETE,
    MUSIC_PROB_REJECT,
    MUSIC_PROB_SEPARATE,
    HPSS_HARM_RATIO_THRESHOLD,
    HPSS_CONTRAST_THRESHOLD,
    HPSS_FLATNESS_THRESHOLD,
    get_quarantine_dir,
)

import config as cfg

logger = get_logger("music_detector")


class MusicDetector:
    """
    Phat hien audio co nhac nen va quyet dinh giu/quarantine/xoa.
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
            logger.info("Music detector initialized (multi-window HPSS + music_prob)")
        except ImportError:
            logger.warning(
                "librosa not installed — using metadata heuristic only. "
                "Install with: pip install librosa"
            )

    def is_music(self, audio_path: Path, metadata: dict | None = None) -> bool:
        """
        Tra ve True neu audio co nhac nen.
        Wrapper backward-compatible cho code cu dung binary check.
        """
        _, music_prob = self.analyze(audio_path, metadata)
        return music_prob >= MUSIC_PROB_SEPARATE

    def analyze(self, audio_path: Path, metadata: dict | None = None) -> tuple[bool, float]:
        """
        Phan tich audio va tra ve (is_music: bool, music_prob: float 0.0-1.0).

        music_prob phan loai 4 nhom:
          >= MUSIC_PROB_REJECT   -> hard reject / quarantine
          >= MUSIC_PROB_SEPARATE -> vocal separation
          >= MUSIC_PROB_AUGMENT  -> giu lam augmentation data
          <  MUSIC_PROB_AUGMENT  -> clean
        """
        if not self._enabled or not cfg.MUSIC_FILTER_ENABLED:
            return False, 0.0

        # Tang 1: Metadata heuristic
        if metadata:
            meta_result = self._check_metadata(metadata)
            if meta_result is True:
                logger.info(f"[metadata] Commercial track flag: {audio_path.name}")
                return True, 1.0

        # Tang 2: Multi-window signal analysis
        if self._has_librosa and audio_path.exists():
            return self._check_signal_multiwindow(audio_path)

        return False, 0.0

    def process(self, audio_path: Path, metadata: dict | None = None) -> tuple[str, float]:
        """
        Kiem tra va phan loai audio theo music_prob.

        Returns:
            ('clean',      prob) -- prob < MUSIC_PROB_SEPARATE : giu nguyen vao audio/
            ('music',      prob) -- prob < MUSIC_PROB_REJECT   : can VocalSeparator
            ('quarantine', prob) -- prob >= MUSIC_PROB_REJECT  : hard reject
        """
        is_music, prob = self.analyze(audio_path, metadata)

        if not is_music:
            return "clean", prob
        if prob >= MUSIC_PROB_REJECT:
            return "quarantine", prob
        return "music", prob

    def quarantine(self, audio_path: Path, crawl_date: str | None = None) -> None:
        """
        Chuyen file vao thu muc quarantine dung theo ngay crawl goc.
        [FIX 1.1] crawl_date de resolve Week/date/quarantine chinh xac.
        """
        qdir = get_quarantine_dir(crawl_date)
        if MUSIC_QUARANTINE_INSTEAD_OF_DELETE:
            qdir.mkdir(parents=True, exist_ok=True)
            dest = qdir / audio_path.name
            shutil.move(str(audio_path), dest)
            logger.warning(f"Quarantined: {audio_path.name} -> {qdir}")
        else:
            audio_path.unlink(missing_ok=True)
            logger.warning(f"Deleted (music): {audio_path.name}")

    # -----------------------------------------
    # Internal helpers
    # -----------------------------------------

    def _check_metadata(self, metadata: dict) -> bool | None:
        """
        Kiem tra metadata tu yt-dlp info_dict.
        Tra ve:
          True -- ro rang co bai hat / ban nhac thuong mai
          None -- can phan tich song am
        """
        platform = metadata.get("platform", "")

        if platform == "tiktok":
            platform_meta = metadata.get("platform_meta", {})
            music_is_original = platform_meta.get("music_is_original")

            if music_is_original is False:
                track = metadata.get("_track", "")
                if track and track.lower() not in (
                    "", "original sound", "am thanh goc", "tieng dong goc"
                ):
                    return True  # Nhac thuong mai co ten ro rang

        return None

    def _check_signal_multiwindow(self, audio_path: Path) -> tuple[bool, float]:
        """
        [UPGRADE 2.2] Phan tich HPSS da cua so: dau / giua / cuoi video.

        Thay vi chi lay 30s dau (bo sot BGM o giua/cuoi), gio phan tich
        toi da 3 cua so 20s va lay MAX probability (conservative approach).

        Returns: (is_music: bool, music_prob: float 0.0-1.0)
        """
        import librosa
        import numpy as np

        try:
            duration = librosa.get_duration(path=str(audio_path))
        except Exception:
            return False, 0.0

        window_sec = min(20.0, MUSIC_ANALYSIS_SAMPLE_SEC * 0.67)

        raw_windows: list[tuple[float, float]] = [
            (0.0,                                           window_sec),  # Dau
            (max(0.0, duration / 2.0 - window_sec / 2.0), window_sec),  # Giua
            (max(0.0, duration - window_sec),               window_sec), # Cuoi
        ]

        # Deduplicate neu video ngan (cac cua so trung nhau)
        seen: set[float] = set()
        unique_windows = []
        for offset, dur in raw_windows:
            key = round(offset, 1)
            if key not in seen:
                seen.add(key)
                unique_windows.append((offset, dur))

        probs: list[float] = []
        for offset, dur in unique_windows:
            p = self._analyze_window(audio_path, offset=offset, duration=dur)
            probs.append(p)
            logger.debug(
                f"[MusicDetector] Window {offset:.0f}s+{dur:.0f}s "
                f"-> prob={p:.3f} | {audio_path.name}"
            )

        if not probs:
            return False, 0.0

        final_prob = float(max(probs))
        is_music = final_prob >= MUSIC_PROB_SEPARATE

        logger.debug(
            f"[MusicDetector] {audio_path.name}: "
            f"probs={[round(p, 3) for p in probs]} max={final_prob:.3f} "
            f"-> {'MUSIC' if is_music else 'SPEECH'}"
        )
        return is_music, final_prob

    def _analyze_window(self, audio_path: Path, offset: float, duration: float) -> float:
        """
        Phan tich mot cua so thoi gian va tra ve music_prob (0.0-1.0).

        [UPGRADE 2.2]:
          - margin=(1.0, 5.0): bao toan phu am xat /s x ch tr/ tieng Viet
          - harm_ratio baseline ha 0.60 -> 0.45
          - contrast baseline ha 22.0 -> 20.0
          - Output: continuous float thay vi binary True/False
        """
        import librosa
        import numpy as np

        try:
            y, sr = librosa.load(
                str(audio_path),
                sr=16000,
                offset=offset,
                duration=duration,
                mono=True,
            )

            if len(y) < sr * 2:  # Qua ngan (< 2s) -> bo qua
                return 0.0

            # 1. HPSS
            y_harm, _ = librosa.effects.hpss(y, margin=(1.0, 5.0))
            e_harm  = float(np.sum(y_harm ** 2))
            e_total = float(np.sum(y ** 2)) + 1e-9
            harm_ratio = e_harm / e_total

            # 2. Spectral Contrast & Flatness
            contrast = float(np.mean(librosa.feature.spectral_contrast(y=y, sr=sr)))
            flatness = float(
                np.mean(librosa.feature.spectral_flatness(y=y, n_fft=2048, hop_length=512))
            )

            # 3. Chuan hoa tung chi so ve [0, 1]
            harm_score     = min(1.0, max(0.0, (harm_ratio - 0.25) / (HPSS_HARM_RATIO_THRESHOLD - 0.25)))
            contrast_score = min(1.0, max(0.0, (contrast   - 10.0) / (HPSS_CONTRAST_THRESHOLD   - 10.0)))
            flatness_score = min(1.0, max(0.0, (HPSS_FLATNESS_THRESHOLD - flatness) / HPSS_FLATNESS_THRESHOLD))

            # 4. Weighted average
            music_prob = (
                0.50 * harm_score
                + 0.30 * contrast_score
                + 0.20 * flatness_score
            )

            return float(np.clip(music_prob, 0.0, 1.0))

        except Exception as exc:
            logger.warning(f"[MusicDetector] Window analysis failed for {audio_path.name}: {exc}")
            return 0.0
