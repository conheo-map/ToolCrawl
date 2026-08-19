"""
processors/vocal_separator.py — Bóc tách và làm sạch giọng nói từ audio có nhạc nền.

Hỗ trợ 2 phương pháp (Dual-Engine):
  1. Engine AI (Demucs - Meta Research): Tách track Vocals bằng Deep Learning (khi có demucs)
  2. Engine Spectral (Librosa + NoiseReduce): Tách Harmonic-Percussive và Spectral Gating (luôn khả dụng, nhẹ, 0MB disk)
"""

import subprocess
import shutil
import tempfile
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("vocal_separator")

DEFAULT_MODEL = "htdemucs_ft"
FALLBACK_MODEL = "htdemucs"


def is_demucs_available() -> bool:
    try:
        result = subprocess.run(["demucs", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_noisereduce_available() -> bool:
    try:
        import noisereduce  # noqa: F401
        import librosa      # noqa: F401
        import soundfile    # noqa: F401
        return True
    except ImportError:
        return False


class VocalSeparator:
    """
    Bóc tách và làm sạch giọng nói khỏi nhạc nền.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model
        self._has_demucs = is_demucs_available()
        self._has_spectral = is_noisereduce_available()

        if self._has_demucs:
            logger.info(f"VocalSeparator: Demucs AI engine ACTIVE (model: {model})")
        elif self._has_spectral:
            logger.info("VocalSeparator: Spectral Vocal Cleaner engine ACTIVE (Librosa + NoiseReduce)")
        else:
            logger.warning("VocalSeparator: No separation engine available. Install noisereduce or demucs.")

    @property
    def available(self) -> bool:
        return self._has_demucs or self._has_spectral

    def separate(self, audio_path: Path, timeout: int = 300) -> bool:
        """
        Bóc tách / làm sạch giọng nói khỏi nhạc nền và ghi đè lại file audio.
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False

        # Ưu tiên Engine 1: Demucs AI nếu có
        if self._has_demucs:
            try:
                success = self._separate_demucs(audio_path, timeout=timeout)
                if success:
                    return True
                logger.warning(f"Demucs failed for {audio_path.name}, falling back to Spectral cleaner...")
            except Exception as exc:
                logger.warning(f"Demucs exception: {exc}, falling back to Spectral cleaner...")

        # Engine 2: Spectral Vocal Cleaner (Luôn hoạt động, nhanh, không tốn disk)
        if self._has_spectral:
            return self._separate_spectral(audio_path)

        logger.warning(f"No separation method available for: {audio_path.name}")
        return False

    # ─────────────────────────────────────────
    # Engine 1: Demucs AI
    # ─────────────────────────────────────────

    def _separate_demucs(self, audio_path: Path, timeout: int) -> bool:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_dir = tmp_path / "output"
            output_dir.mkdir()

            logger.info(f"[Demucs AI] Separating vocals: {audio_path.name} ...")
            cmd = [
                "demucs",
                "--model", self._model,
                "--two-stems", "vocals",
                "--out", str(output_dir),
                str(audio_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.warning(f"[Demucs AI] Primary model failed, trying fallback: {FALLBACK_MODEL}")
                cmd[2] = FALLBACK_MODEL
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                if result.returncode != 0:
                    return False

            vocals_file = None
            for ext in ["wav", "mp3"]:
                matches = list(output_dir.rglob(f"vocals.{ext}"))
                if matches:
                    vocals_file = matches[0]
                    break

            if not vocals_file:
                return False

            return self._convert_to_wav(src=vocals_file, dst=audio_path)

    # ─────────────────────────────────────────
    # Engine 2: Spectral Vocal Cleaner
    # ─────────────────────────────────────────

    def _separate_spectral(self, audio_path: Path) -> bool:
        """
        Tách giọng nói 3 tầng siêu mạnh:
          Tầng 1: HPSS — tách thành phần Harmonic (nhạc cụ) và Percussive (trống)
                   → Chỉ giữ lại phần Residual (giọng nói)
          Tầng 2: Spectral Gating mạnh (prop_decrease=0.97)
                   → Xóa sạch tần số nhạc nền còn sót lại
          Tầng 3: High-pass filter 80Hz
                   → Loại bỏ hoàn toàn tiếng bass và âm nhạc cụ tần số thấp
        """
        import librosa
        import soundfile as sf
        import noisereduce as nr
        import numpy as np

        try:
            logger.info(f"[Spectral 3-Layer] Isolating vocals from: {audio_path.name}")
            y, sr = librosa.load(str(audio_path), sr=16000, mono=True)

            # ── Tầng 1: HPSS — Tách Harmonic (nhạc cụ) khỏi Percussive + Vocal ──
            # margin=3 → càng lớn càng mạnh tay với nhạc nền
            harmonic, percussive = librosa.effects.hpss(y, margin=3)
            # Giọng nói nằm trong phần residual (y trừ đi harmonic)
            vocals_approx = y - harmonic * 0.9

            # ── Tầng 2: Spectral Gating mạnh ──
            # Dùng chính phần harmonic làm noise profile để xóa nhạc cụ
            noise_clip = harmonic
            vocals_clean = nr.reduce_noise(
                y=vocals_approx,
                y_noise=noise_clip,
                sr=sr,
                stationary=False,
                prop_decrease=0.97,       # Xóa 97% nhạc nền
                time_constant_s=0.5,
                freq_mask_smooth_hz=500,
                n_fft=2048,
            )

            # ── Tầng 3: High-pass filter 80Hz (xóa bass và kick drum) ──
            from scipy.signal import butter, sosfilt
            sos = butter(5, 80.0 / (sr / 2), btype='high', output='sos')
            vocals_clean = sosfilt(sos, vocals_clean)

            # Normalize amplitude về -1 đến 1
            max_amp = np.max(np.abs(vocals_clean))
            if max_amp > 0:
                vocals_clean = vocals_clean / max_amp * 0.95

            # Ghi đè file WAV chuẩn 16kHz mono PCM 16-bit
            tmp_out = audio_path.parent / f"_tmp_{audio_path.name}"
            sf.write(str(tmp_out), vocals_clean.astype(np.float32), sr, subtype="PCM_16")

            if tmp_out.exists() and tmp_out.stat().st_size > 1000:
                shutil.move(str(tmp_out), str(audio_path))
                logger.info(f"[Spectral 3-Layer] Completed: {audio_path.name}")
                return True
            else:
                tmp_out.unlink(missing_ok=True)
                return False

        except Exception as exc:
            logger.error(f"[Spectral 3-Layer] Failed for {audio_path.name}: {exc}", exc_info=True)
            return False

    def _convert_to_wav(self, src: Path, dst: Path) -> bool:
        tmp_out = dst.parent / f"_tmp_sep_{dst.name}"
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
            str(tmp_out),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and tmp_out.exists():
                shutil.move(str(tmp_out), str(dst))
                logger.info(f"[Demucs AI] Done: {dst.name} ({dst.stat().st_size // 1024} KB)")
                return True
            else:
                tmp_out.unlink(missing_ok=True)
                return False
        except Exception:
            tmp_out.unlink(missing_ok=True)
            return False
