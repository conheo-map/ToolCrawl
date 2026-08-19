import subprocess
import pytest
from pathlib import Path
from processors.audio_converter import convert_to_wav, verify_audio
from config import AUDIO_SAMPLE_RATE, AUDIO_CHANNELS

def test_convert_and_verify_audio(tmp_path: Path):
    # Generate a 1-second sine wave test mp3 using ffmpeg
    raw_mp3 = tmp_path / "test_input.mp3"
    gen_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=1000:duration=2",
        "-c:a", "libmp3lame",
        str(raw_mp3)
    ]
    res = subprocess.run(gen_cmd, capture_output=True)
    assert res.returncode == 0
    assert raw_mp3.exists()

    # Convert to WAV 16kHz mono PCM s16le
    out_wav = tmp_path / "test_output.wav"
    duration = convert_to_wav(raw_mp3, out_wav)

    assert out_wav.exists()
    assert 1.9 <= duration <= 2.1

    # Verify specs using ffprobe wrapper
    info = verify_audio(out_wav)
    assert info["sample_rate"] == AUDIO_SAMPLE_RATE  # 16000
    assert info["channels"] == AUDIO_CHANNELS        # 1
    assert "pcm_s16le" in info["codec"] or "pcm_s16" in info["codec"]
