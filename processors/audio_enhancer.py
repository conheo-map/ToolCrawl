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

        # Chuỗi bộ lọc DSP ASR Master Grade bảo toàn thanh điệu tiếng Việt:
        # 1. Highpass (75Hz): Cắt rung mic nhưng bảo toàn F0 thanh Huyền (80Hz - 120Hz)
        # 2. Lowpass (7600Hz): Khử tiếng xì hiss, bảo toàn phụ âm gió s, x, tr, ch
        # 3. Transparent Denoise (afftdn nf=-35, nr=10): Khử ồn nền mà không làm bẹt thanh Nặng/Ngã
        # 4. De-mud (300Hz EQ, -1.5dB): Khử tiếng đục, dội phòng nhẹ nhàng
        # 5. Presence Boost (3.2kHz EQ, +1.8dB): Làm rõ nét mút âm phụ âm tiếng Việt
        # 6. EBU R128 Loudnorm: -16 LUFS, True-Peak an toàn -1.0 dBFS (loại bỏ dynaudnorm để chống méo pumping)
        filter_chain = (
            "highpass=f=75,"
            "lowpass=f=7600,"
            "afftdn=nf=-35:nr=10:nt=w,"
            "equalizer=f=300:t=q:w=1.5:g=-1.5,"
            "equalizer=f=3200:t=q:w=1.0:g=1.8,"
            "loudnorm=I=-16:TP=-1.0:LRA=11"
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
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
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
