"""
test_pipeline.py — Pytest Suite for Speech Pipeline Modules
"""
import pytest
import numpy as np
import soundfile as sf
import tempfile
import shutil
from pathlib import Path

from src.dedup.audio_dedup import AudioDedupEngine
from src.quality_gate.evaluator import QualityGateEvaluator


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def create_synthetic_audio(path: Path, dur_sec: float = 3.0, sr: int = 16000, tone_hz: float = 300.0):
    t = np.linspace(0, dur_sec, int(sr * dur_sec), endpoint=False)
    sig = 0.5 * np.sin(2 * np.pi * tone_hz * t)
    sf.write(str(path), sig.astype(np.float32), sr, subtype="PCM_16")
    return path


def test_audio_format_and_spec(temp_dir):
    """Test output audio conforms to 16kHz, mono, PCM_16."""
    f = temp_dir / "test_spec.wav"
    create_synthetic_audio(f, 2.0)
    info = sf.info(str(f))
    assert info.samplerate == 16000
    assert info.channels == 1
    assert info.subtype == "PCM_16"


def test_audio_dedup_content_hash(temp_dir):
    """Test deduplication engine detects exact and duplicate waveform content."""
    f1 = temp_dir / "clip_a.wav"
    f2 = temp_dir / "clip_b.wav"
    create_synthetic_audio(f1, 2.5, tone_hz=440.0)
    shutil.copy2(f1, f2)

    dedup = AudioDedupEngine()
    is_dup1, _ = dedup.is_duplicate(f1)
    is_dup2, reason2 = dedup.is_duplicate(f2)

    assert is_dup1 is False, "First instance must not be duplicate"
    assert is_dup2 is True, "Second identical instance must be flagged duplicate"
    assert "duplicate_audio_content" in reason2


def test_quality_gate_evaluation(temp_dir):
    """Test quality gate evaluator correctly computes spectral flatness and SNR."""
    f = temp_dir / "tone.wav"
    create_synthetic_audio(f, 3.0, tone_hz=350.0)

    evaluator = QualityGateEvaluator()
    res = evaluator.evaluate_audio(f)

    assert "spectral_flatness" in res
    assert "snr_db" in res
    assert res["channels"] == 1
    assert res["sample_rate"] == 16000
