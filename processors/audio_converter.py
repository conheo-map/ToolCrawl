"""
processors/audio_converter.py — Chuyển đổi audio về WAV 16kHz mono
và xác nhận spec bằng ffprobe.
"""

import subprocess
import json
import shutil
from pathlib import Path
from utils.logger import get_logger
from config import AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_CODEC

logger = get_logger("audio_converter")


def _check_ffmpeg() -> bool:
    """Kiểm tra FFmpeg có trong PATH không."""
    return shutil.which("ffmpeg") is not None


def _check_ffprobe() -> bool:
    """Kiểm tra ffprobe có trong PATH không."""
    return shutil.which("ffprobe") is not None


def convert_to_wav(input_path: Path, output_path: Path) -> float:
    """
    Chuyển đổi `input_path` sang WAV 16kHz mono PCM S16LE.
    Trả về duration_seconds của file output.
    Raise RuntimeError nếu FFmpeg lỗi.
    """
    if not _check_ffmpeg():
        raise EnvironmentError(
            "ffmpeg not found in PATH. Please install FFmpeg.\n"
            "  Windows: winget install FFmpeg\n"
            "  Or download from https://ffmpeg.org/download.html"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",                        # Overwrite output
        "-i", str(input_path),
        "-vn",                       # Bỏ video stream
        "-acodec", AUDIO_CODEC,      # pcm_s16le
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-ac", str(AUDIO_CHANNELS),
        "-f", "wav",
        str(output_path),
    ]

    logger.debug(f"Converting: {input_path.name} -> {output_path.name}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 phút tối đa
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed for {input_path.name}:\n{result.stderr[-500:]}"
        )

    # Xác nhận và lấy duration
    info = verify_audio(output_path)
    return info["duration_seconds"]


def verify_audio(path: Path) -> dict:
    """
    Dùng ffprobe để xác nhận thông số audio.
    Trả về dict với: sample_rate, channels, codec, format, duration_seconds.
    Raise ValueError nếu không đạt chuẩn.
    """
    if not _check_ffprobe():
        raise EnvironmentError(
            "ffprobe not found in PATH. Please install FFmpeg."
        )

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise ValueError(f"No audio stream found in {path}")

    stream = audio_streams[0]
    sample_rate = int(stream.get("sample_rate", 0))
    channels = int(stream.get("channels", 0))
    codec_name = stream.get("codec_name", "")
    duration = float(fmt.get("duration", stream.get("duration", 0)))

    info = {
        "sample_rate": sample_rate,
        "channels": channels,
        "codec": codec_name,
        "duration_seconds": round(duration, 3),
        "format": fmt.get("format_name", ""),
    }

    # Validate
    errors = []
    if sample_rate != AUDIO_SAMPLE_RATE:
        errors.append(f"sample_rate={sample_rate} (expected {AUDIO_SAMPLE_RATE})")
    if channels != AUDIO_CHANNELS:
        errors.append(f"channels={channels} (expected {AUDIO_CHANNELS})")
    if "pcm_s16" not in codec_name:
        errors.append(f"codec={codec_name} (expected pcm_s16le)")

    if errors:
        raise ValueError(
            f"Audio spec mismatch for {path.name}: {'; '.join(errors)}"
        )

    logger.debug(
        f"Verified {path.name}: {sample_rate}Hz, {channels}ch, {duration:.1f}s"
    )
    return info
