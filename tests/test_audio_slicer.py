"""
tests/test_audio_slicer.py — Unit test cho Smart Audio Slicer.
"""

import subprocess
from pathlib import Path
from processors.audio_slicer import AudioSlicer
import pytest

@pytest.fixture
def dummy_long_wav(tmp_path: Path) -> Path:
    """Tạo 1 file wav giả lập 45 giây có 2 đoạn ngắt tiếng để test cắt."""
    wav_file = tmp_path / "test_long.wav"
    # Tạo 45s audio với tone và silence xen kẽ
    # 0-15s tone 440Hz, 15-16s silence, 16-30s tone 440Hz, 30-31s silence, 31-45s tone 440Hz
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=45",
        "-ar", "16000",
        "-ac", "1",
        str(wav_file)
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0
    return wav_file

@pytest.fixture
def dummy_short_wav(tmp_path: Path) -> Path:
    """Tạo 1 file wav giả lập 15 giây (không cần cắt)."""
    wav_file = tmp_path / "test_short.wav"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=15",
        "-ar", "16000",
        "-ac", "1",
        str(wav_file)
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0
    return wav_file


def test_audio_slicer_short(dummy_short_wav: Path, tmp_path: Path):
    slicer = AudioSlicer(max_segment_sec=30.0, min_segment_sec=5.0)
    out_dir = tmp_path / "out_short"
    slices = slicer.slice_audio(dummy_short_wav, "tt_short_01", out_dir)
    assert len(slices) == 1
    assert slices[0]["item_id"] == "tt_short_01"
    assert 14.0 <= slices[0]["duration_seconds"] <= 16.0


def test_audio_slicer_long(dummy_long_wav: Path, tmp_path: Path):
    slicer = AudioSlicer(max_segment_sec=30.0, min_segment_sec=5.0)
    out_dir = tmp_path / "out_long"
    slices = slicer.slice_audio(dummy_long_wav, "tt_long_01", out_dir)
    assert len(slices) >= 2
    for s in slices:
        assert 5.0 <= s["duration_seconds"] <= 30.5
        assert Path(s["audio_path"]).exists()
