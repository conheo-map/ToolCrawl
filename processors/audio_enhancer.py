"""
processors/audio_enhancer.py — Tăng cường chất lượng âm thanh giọng nói chuyên sâu cho ASR.

Giải quyết 3 vấn đề phổ biến của audio mạng xã hội:
  1. Dính nhạc nền nhỏ / tạp âm nền còn sót lại -> Lọc High-pass/Low-pass & Spectral Noise Filter.
  2. Nói không rõ chữ / giọng bị đục hoặc ồm -> Tăng cường độ rõ phụ âm (Speech Presence EQ 3kHz) & Khử đục (De-mud 300Hz).
  3. Nói đoạn to đoạn nhỏ -> Cân bằng âm lượng động (Dynamic Audio Normalizer - dynaudnorm) & EBU R128.
"""

import subprocess
import shutil
from pathlib import Path
from utils.logger import get_logger
from config import AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_CODEC

logger = get_logger("audio_enhancer")


class SpeechEnhancer:
    """
    Bộ xử lý tăng cường độ rõ giọng nói và cân bằng âm lượng tự động.
    """

    def __init__(self) -> None:
        self._has_ffmpeg = shutil.which("ffmpeg") is not None

    def enhance(self, audio_path: Path) -> bool:
        """
        Xử lý tăng cường trực tiếp trên file audio WAV:
          - Khử tạp âm & bass nhạc nền nhỏ (<80Hz, >7.6kHz)
          - Khử ồm ồm phòng (De-mud 300Hz)
          - Tăng độ sắc nét của từ ngữ/phụ âm (+2.5dB @ 3kHz)
          - Cân bằng tự động đoạn nói to / nói nhỏ (Dynamic Normalization)
          - Chuẩn hóa âm lượng EBU R128 (-16 LUFS)
        """
        if not self._has_ffmpeg or not audio_path.exists():
            return False

        tmp_out = audio_path.with_suffix(".enhanced.tmp.wav")

        # Chuỗi bộ lọc DSP 7 tầng chuẩn studio cho Voice / ASR:
        # 1. Highpass + Lowpass: Cắt bỏ dải tần siêu trầm (<80Hz) & dải tần xì xào (>7.6kHz)
        # 2. FFT Adaptive Denoise (afftdn): Khử tiếng ồn quạt, gió, tạp âm mic nền
        # 3. Silence Trimmer (silenceremove): Cắt bỏ 100% các đoạn câm lặng ở đầu, đuôi và khoảng lặng dài
        # 4. De-mud (300Hz EQ): Khử tiếng đục, dội âm phòng
        # 5. Presence Boost (3kHz EQ): Tăng độ sắc nét của phụ âm tiếng Việt
        # 6. Dynamic Normalizer (dynaudnorm): Cân bằng tự động đoạn nói to / nói nhỏ
        # 7. EBU R128 Loudnorm: Chuẩn hóa âm lượng đầu ra -16 LUFS
        filter_chain = (
            "highpass=f=80,"
            "lowpass=f=7600,"
            "afftdn=nf=-25,"
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB:stop_periods=-1:stop_duration=0.8:stop_threshold=-50dB,"
            "equalizer=f=300:t=q:w=1.5:g=-2,"
            "equalizer=f=3000:t=q:w=1.0:g=2.5,"
            "dynaudnorm=f=120:g=15:p=0.95:m=10,"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-af", filter_chain,
            "-acodec", AUDIO_CODEC,
            "-ar", str(AUDIO_SAMPLE_RATE),
            "-ac", str(AUDIO_CHANNELS),
            "-f", "wav",
            str(tmp_out),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 1000:
                tmp_out.replace(audio_path)
                logger.debug(f"[SpeechEnhancer] Enhanced speech clarity & normalized volume: {audio_path.name}")
                return True
            else:
                if tmp_out.exists():
                    tmp_out.unlink()
                logger.debug(f"[SpeechEnhancer] FFmpeg notice for {audio_path.name}: {res.stderr[-200:]}")
                return False
        except Exception as exc:
            if tmp_out.exists():
                tmp_out.unlink()
            logger.debug(f"[SpeechEnhancer] Enhance exception for {audio_path.name}: {exc}")
            return False
