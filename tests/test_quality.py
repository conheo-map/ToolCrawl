"""
test_quality.py — Unit Tests for Quality Filter Pipeline & Audit Rules
"""
import pytest
import numpy as np
import soundfile as sf
from pathlib import Path
import tempfile
import shutil

from tools.quality_filter_pipeline import (
    compute_audio_hash,
    normalize_and_write,
    check_music_ratio,
    process_file,
    TARGET_SR,
    TARGET_SUBTYPE,
)


@pytest.fixture
def temp_audio_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def create_synthetic_wav(path: Path, duration_sec: float = 3.0, sr: int = 16000, tone_hz: float = 440.0):
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    # Sine tone with gentle envelope
    audio = 0.5 * np.sin(2 * np.pi * tone_hz * t)
    # Fade in/out
    fade = int(sr * 0.05)
    audio[:fade] *= np.linspace(0, 1, fade)
    audio[-fade:] *= np.linspace(1, 0, fade)
    sf.write(str(path), audio, samplerate=sr, subtype="PCM_16")
    return path


def create_silence_wav(path: Path, duration_sec: float = 3.0, sr: int = 16000):
    audio = np.zeros(int(sr * duration_sec), dtype=np.float32)
    sf.write(str(path), audio, samplerate=sr, subtype="PCM_16")
    return path


def test_audio_hash_dedup():
    """Test SHA256 hash dedup logic accurately identifies identical waveforms."""
    audio1 = np.sin(np.linspace(0, 10, 16000))
    audio2 = np.copy(audio1)
    audio3 = np.sin(np.linspace(0, 10, 16000) * 1.5)

    hash1 = compute_audio_hash(audio1)
    hash2 = compute_audio_hash(audio2)
    hash3 = compute_audio_hash(audio3)

    assert hash1 == hash2, "Identical audio should yield exact same hash"
    assert hash1 != hash3, "Different audio should yield different hash"


def test_audio_normalization_format(temp_audio_dir):
    """Test audio is correctly exported as 16kHz, mono, 16-bit PCM."""
    out_file = temp_audio_dir / "norm_test.wav"
    audio = np.random.uniform(-0.8, 0.8, 16000 * 2).astype(np.float32)

    normalize_and_write(audio, TARGET_SR, out_file)
    assert out_file.exists()

    info = sf.info(str(out_file))
    assert info.samplerate == 16000
    assert info.channels == 1
    assert info.subtype == TARGET_SUBTYPE
    assert pytest.approx(info.duration, rel=1e-2) == 2.0


def test_music_ratio_flatness():
    """Test spectral flatness on pure tone vs white noise."""
    sr = 16000
    t = np.linspace(0, 2, sr * 2, endpoint=False)
    # Pure tone = speech/harmonic-like (low flatness)
    tone = np.sin(2 * np.pi * 300 * t)
    # Noise = high flatness
    noise = np.random.normal(0, 0.5, sr * 2)

    m_tone, flat_tone = check_music_ratio(tone, sr)
    m_noise, flat_noise = check_music_ratio(noise, sr)

    assert flat_tone < flat_noise, "Tonal audio should have lower spectral flatness than noise"


def test_process_file_duplicate_rejection(temp_audio_dir):
    """Test pipeline rejects duplicate audio files."""
    f1 = temp_audio_dir / "audio1.wav"
    f2 = temp_audio_dir / "audio2.wav"
    create_synthetic_wav(f1, 2.5)
    shutil.copy2(f1, f2)

    out_dir = temp_audio_dir / "out"
    seen_hashes = {}

    # Mock VAD check to avoid internet/model download dependence during fast tests if needed
    res1 = process_file(f1, out_dir, seen_hashes, source_id="id1")
    res2 = process_file(f2, out_dir, seen_hashes, source_id="id2")

    # Second file must be rejected as duplicate
    assert res2["status"] == "rejected"
    assert "duplicate" in res2["reject_reason"]
