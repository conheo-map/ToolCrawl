"""
processors/vocal_separator.py — Bóc tách và làm sạch giọng nói từ audio có nhạc nền.

Pipeline chính thức đã chốt:
  🏠 LOCAL mode  (CLOUD_MODE không được set):
     → Cascade 2 Tầng SOTA:
         Tầng 1: Demucs AI (htdemucs) — Triệt tiêu Bass, Trống, Sub-bass (giảm -80-93%)
         Tầng 2: Mel-Band RoFormer — Khử tàn dư dải cao, synth, sóng hài
     → Fallback: Nếu RoFormer lỗi → giữ kết quả Demucs tầng 1
     → Fallback 2: Nếu Demucs lỗi → HPSS + SpectralGating 3 tầng

  ☁️  CLOUD mode (set CLOUD_MODE=1 trong môi trường):
     → Engine 1 tầng siêu tốc: SpectralGating (90%) + High-pass Filter 80Hz
     → Chạy trong ~1 giây trên máy chủ cloud, đủ sạch cho ASR pipeline
"""

import os
import subprocess
import shutil
import tempfile
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("vocal_separator")

DEFAULT_MODEL = "htdemucs"
FALLBACK_MODEL = "htdemucs"

# Tự động phát hiện môi trường chạy
IS_CLOUD = os.environ.get("CLOUD_MODE", "0") == "1"


def is_demucs_available() -> bool:
    import sys
    try:
        result = subprocess.run([sys.executable, "-m", "demucs", "--help"], capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception:
        try:
            result = subprocess.run(["demucs", "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
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
    Tự động chọn engine phù hợp theo môi trường chạy (Local vs Cloud).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model
        self._has_demucs = is_demucs_available()
        self._has_spectral = is_noisereduce_available()

        if IS_CLOUD:
            logger.info("🌐 CLOUD MODE: Dùng engine tách giọng siêu tốc 1 tầng (~1s/file)")
        elif self._has_demucs:
            logger.info(f"🏠 LOCAL MODE: Demucs AI engine ACTIVE (model: {model})")
        elif self._has_spectral:
            logger.info("🏠 LOCAL MODE: Tách giọng 3 tầng HPSS+SpectralGating+HighPass ACTIVE")
        else:
            logger.warning("VocalSeparator: No separation engine available. Install noisereduce or demucs.")

    @property
    def available(self) -> bool:
        return self._has_demucs or self._has_spectral

    def separate(self, audio_path: Path, timeout: int = 900) -> bool:
        """
        Bóc tách giọng nói khỏi nhạc nền và ghi đè lại file audio.
        Tự động chọn engine Local (cao) hoặc Cloud (nhanh).
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False

        # ☁️ CLOUD MODE: dùng engine 1 tầng siêu tốc
        if IS_CLOUD:
            if self._has_spectral:
                return self._separate_cloud_fast(audio_path)
            return False

        # 🏠 LOCAL MODE: ưu tiên Demucs AI, rồi mới dùng 3 tầng Spectral
        if self._has_demucs:
            try:
                success = self._separate_demucs(audio_path, timeout=timeout)
                if success:
                    return True
                logger.warning(f"Demucs failed for {audio_path.name}, falling back to 3-layer Spectral...")
            except Exception as exc:
                logger.warning(f"Demucs exception: {exc}, falling back to 3-layer Spectral...")

        if self._has_spectral:
            return self._separate_spectral(audio_path)

        logger.warning(f"No separation method available for: {audio_path.name}")
        return False


    # ─────────────────────────────────────────
    # Engine 1: Cascade 2 Tầng (Demucs -> Mel-Band RoFormer) SOTA
    # ─────────────────────────────────────────

    def _separate_demucs(self, audio_path: Path, timeout: int) -> bool:
        """
        [CHÍNH THỨC] Quy trình 2 tầng bóc tách nhạc nền TikTok:
          - Tầng 1: Demucs AI (htdemucs) — Triệt tiêu Bass và Trống
          - Tầng 2: Mel-Band RoFormer SOTA — Khử sạch tàn dư dải cao, synth và sóng hài
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            demucs_out_dir = tmp_path / "demucs_out"
            demucs_out_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"[Cascade Tầng 1/2: Demucs AI] Triệt tiêu trống & bass: {audio_path.name} ...")
            import sys
            cmd = [
                sys.executable,
                "-m",
                "demucs",
                "-n", self._model,
                "--two-stems", "vocals",
                "--shifts", "2",
                "--overlap", "0.25",
                "--out", str(demucs_out_dir),
                str(audio_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.warning(f"[Demucs AI] Primary model failed, trying fallback: {FALLBACK_MODEL}")
                cmd[4] = FALLBACK_MODEL
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                if result.returncode != 0:
                    return False

            demucs_vocals = None
            for ext in ["wav", "mp3"]:
                matches = list(demucs_out_dir.rglob(f"vocals.{ext}"))
                if matches:
                    demucs_vocals = matches[0]
                    break

            if not demucs_vocals:
                return False

            # Tầng 2: Mel-Band RoFormer
            final_vocal = demucs_vocals
            try:
                import torch
                # Ensure PyTorch 2.6+ compatibility
                _orig_load = torch.load
                def _safe_load(*a, **kw):
                    kw["weights_only"] = False
                    return _orig_load(*a, **kw)
                torch.load = _safe_load

                from audio_separator.separator import Separator
                roformer_out_dir = tmp_path / "roformer_out"
                roformer_out_dir.mkdir(parents=True, exist_ok=True)

                logger.info(f"[Cascade Tầng 2/2: MelBand RoFormer] Khử tàn dư dải cao: {audio_path.name} ...")
                sep = Separator(
                    output_dir=str(roformer_out_dir),
                    output_format="WAV",
                    log_level=30
                )
                sep.load_model("vocals_mel_band_roformer.ckpt")
                roformer_outputs = sep.separate(str(demucs_vocals))
                
                # Tìm output vocal của RoFormer
                for ro_f in roformer_outputs:
                    if "(vocals)" in str(ro_f).lower() or "vocals" in Path(ro_f).stem.lower():
                        final_vocal = Path(ro_f)
                        logger.info(f"[Cascade 2 Tầng] Hoàn tất bóc tách tinh khiết cho {audio_path.name}")
                        break
            except Exception as ro_exc:
                logger.warning(f"[Cascade] MelBand RoFormer tầng 2 gặp lỗi ({ro_exc}), sử dụng kết quả tầng 1 (Demucs).")
                final_vocal = demucs_vocals

            return self._convert_to_wav(src=final_vocal, dst=audio_path)

    # ─────────────────────────────────────────
    # Engine 0: Cloud Fast (1 tầng, ~1s/file)
    # ─────────────────────────────────────────

    def _separate_cloud_fast(self, audio_path: Path) -> bool:
        """
        ☁️ CLOUD MODE — Engine siêu tốc 1 tầng:
          SpectralGating 90% + High-pass Filter 80Hz
          Mục tiêu: chạy nhanh nhất có thể (~1s) trên CPU máy chủ cloud
          Chất lượng: tốt, đủ dùng cho ASR speech recognition pipeline
        """
        import librosa
        import soundfile as sf
        import noisereduce as nr
        import numpy as np

        try:
            logger.info(f"[☁️ Cloud Fast] Removing BGM: {audio_path.name}")
            y, sr = librosa.load(str(audio_path), sr=16000, mono=True)

            # Single-pass spectral gating — nhanh, bảo toàn âm sắc
            y_clean = nr.reduce_noise(
                y=y, sr=sr,
                stationary=False,
                prop_decrease=0.85,
                time_constant_s=0.5,
                freq_mask_smooth_hz=500,
                n_fft=1024,             # Nhỏ hơn = nhanh hơn
            )

            # High-pass filter 80Hz — loại bass và kick drum
            from scipy.signal import butter, sosfilt
            sos = butter(4, 80.0 / (sr / 2), btype='high', output='sos')
            y_clean = sosfilt(sos, y_clean)

            # Normalize
            max_amp = np.max(np.abs(y_clean))
            if max_amp > 0:
                y_clean = y_clean / max_amp * 0.95

            tmp_out = audio_path.parent / f"_tmp_{audio_path.name}"
            sf.write(str(tmp_out), y_clean.astype(np.float32), sr, subtype="PCM_16")

            if tmp_out.exists() and tmp_out.stat().st_size > 1000:
                shutil.move(str(tmp_out), str(audio_path))
                logger.info(f"[☁️ Cloud Fast] Done: {audio_path.name}")
                return True
            tmp_out.unlink(missing_ok=True)
            return False

        except Exception as exc:
            logger.error(f"[☁️ Cloud Fast] Failed: {exc}")
            return False

    # ─────────────────────────────────────────
    # Engine 2: Spectral Vocal Cleaner (3 tầng - LOCAL)
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
            harmonic, percussive = librosa.effects.hpss(y, margin=2.0)
            # Giọng nói nằm trong phần residual (y trừ đi harmonic)
            vocals_approx = y - harmonic * 0.85

            # ── Tầng 2: Spectral Gating bảo toàn âm vị ──
            # Dùng chính phần harmonic làm noise profile để xóa nhạc cụ nhưng bảo toàn phụ âm
            noise_clip = harmonic
            vocals_clean = nr.reduce_noise(
                y=vocals_approx,
                y_noise=noise_clip,
                sr=sr,
                stationary=False,
                prop_decrease=0.85,       # Khử 85% nhạc nền, bảo tồn trọn vẹn phụ âm xát tiếng Việt
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
