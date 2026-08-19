"""
processors/vocal_separator.py — Bóc tách giọng nói từ audio có nhạc nền.

Sử dụng Demucs (Meta AI) — mô hình tách âm thanh hàng đầu thế giới.
Mô hình htdemucs_ft chuyên biệt tách track Vocals với chất lượng cao nhất.

Pipeline:
  1. Nhận file WAV 16kHz Mono (đã qua ffmpeg)
  2. Demucs tách thành track Vocals + Accompaniment
  3. Chỉ lấy track Vocals, convert lại về 16kHz Mono WAV chuẩn ASR
  4. Trả về đường dẫn file mới (ghi đè lên file gốc)
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


class VocalSeparator:
    """
    Bóc tách giọng nói khỏi nhạc nền bằng mô hình Demucs AI (Meta Research).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model
        self._available = is_demucs_available()
        if self._available:
            logger.info(f"VocalSeparator initialized with model: {model}")
        else:
            logger.warning(
                "demucs not installed — vocal separation unavailable. "
                "Videos with music will be quarantined instead of cleaned."
            )

    @property
    def available(self) -> bool:
        return self._available

    def separate(self, audio_path: Path, timeout: int = 300) -> bool:
        if not self._available:
            logger.warning(f"Demucs unavailable, cannot separate: {audio_path.name}")
            return False

        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_dir = tmp_path / "output"
            output_dir.mkdir()

            logger.info(f"[Demucs] Separating vocals: {audio_path.name} ...")

            cmd = [
                "demucs",
                "--model", self._model,
                "--two-stems", "vocals",
                "--out", str(output_dir),
                str(audio_path),
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.error(f"[Demucs] Timeout ({timeout}s) separating: {audio_path.name}")
                return False

            if result.returncode != 0:
                if self._model != FALLBACK_MODEL:
                    logger.warning(f"[Demucs] Model {self._model} failed, trying {FALLBACK_MODEL} ...")
                    return self._try_fallback(audio_path, output_dir, timeout)
                logger.error(f"[Demucs] Separation failed: {result.stderr[-500:]}")
                return False

            vocals_file = self._find_vocals_file(output_dir)
            if not vocals_file:
                logger.error(f"[Demucs] Vocals file not found for: {audio_path.name}")
                return False

            return self._convert_to_wav(src=vocals_file, dst=audio_path)

    def _try_fallback(self, audio_path: Path, output_dir: Path, timeout: int) -> bool:
        cmd = [
            "demucs", "--model", FALLBACK_MODEL,
            "--two-stems", "vocals",
            "--out", str(output_dir / "fallback"),
            str(audio_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                vocals_file = self._find_vocals_file(output_dir / "fallback")
                if vocals_file:
                    return self._convert_to_wav(src=vocals_file, dst=audio_path)
        except subprocess.TimeoutExpired:
            pass
        return False

    def _find_vocals_file(self, output_dir: Path) -> Path | None:
        for ext in ["wav", "mp3"]:
            matches = list(output_dir.rglob(f"vocals.{ext}"))
            if matches:
                return matches[0]
        return None

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
                logger.info(f"[Demucs] Done: {dst.name} ({dst.stat().st_size // 1024} KB)")
                return True
            else:
                tmp_out.unlink(missing_ok=True)
                logger.error(f"[Demucs] FFmpeg failed: {result.stderr[-300:]}")
                return False
        except Exception as exc:
            tmp_out.unlink(missing_ok=True)
            logger.error(f"[Demucs] Error: {exc}")
            return False
