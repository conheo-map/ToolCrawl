"""
tests/test_quality_assessor.py — Unit test cho QualityAssessor.
"""

import math
import struct
import wave
from pathlib import Path
import pytest
from processors.quality_assessor import QualityAssessor


def create_synthetic_wav(path: Path, sample_rate: int = 16000, duration: float = 2.0, has_speech: bool = True) -> None:
    """Tạo file WAV nhân tạo với khoảng lặng và đoạn nói để kiểm thử."""
    n_samples = int(sample_rate * duration)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        
        samples = []
        for i in range(n_samples):
            # Nửa đầu là speech, nửa sau là silence/nhiễu cực nhỏ
            if has_speech and (i < n_samples * 0.6):
                val = 0.5 * math.sin(2 * math.pi * 300 * i / sample_rate) + 0.3 * math.sin(2 * math.pi * 1000 * i / sample_rate)
            else:
                val = 0.0001 * math.sin(2 * math.pi * 5000 * i / sample_rate)
            int_val = int(val * 32767)
            samples.append(int_val)
            
        raw = struct.pack(f"<{n_samples}h", *samples)
        wav.writeframes(raw)


def test_quality_assessor_clean_audio(tmp_path: Path):
    clean_wav = tmp_path / "clean_test.wav"
    create_synthetic_wav(clean_wav, has_speech=True)
    
    assessor = QualityAssessor(min_snr_db=10.0)
    stats = assessor.assess(clean_wav)
    
    assert "snr_db" in stats
    assert "quality_score" in stats
    assert stats["snr_db"] > 5.0
    assert stats["speech_ratio"] > 0.0
    assert stats["peak_dbfs"] < 0.0
    assert stats["quality_score"] > 0.40


def test_quality_assessor_missing_file(tmp_path: Path):
    missing_wav = tmp_path / "non_existent.wav"
    assessor = QualityAssessor()
    stats = assessor.assess(missing_wav)
    assert stats["is_clean"] is False
    assert stats["quality_score"] == 0.0
