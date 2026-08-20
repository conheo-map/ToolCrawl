"""
tests/test_audio_enhancer.py — Unit test cho bộ tăng cường chất lượng âm thanh giọng nói.
"""

import numpy as np
import soundfile as sf
import tempfile
from pathlib import Path
from processors.audio_enhancer import SpeechEnhancer
from processors.audio_converter import verify_audio


def test_speech_enhancer():
    enhancer = SpeechEnhancer()
    
    # Tạo một file wav test 16kHz mono có tín hiệu âm thanh
    sr = 16000
    duration_s = 2.0
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # Tổng hợp sóng mô phỏng giọng nói + tạp âm
    signal = 0.5 * np.sin(2 * np.pi * 300 * t) + 0.3 * np.sin(2 * np.pi * 3000 * t)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_wav = Path(tmpdir) / "test_raw.wav"
        sf.write(str(test_wav), signal, sr, subtype="PCM_16")

        success = enhancer.enhance(test_wav)
        assert success is True
        assert test_wav.exists()

        # Kiểm tra file output vẫn đạt chuẩn ASR 16kHz mono
        info = verify_audio(test_wav)
        assert info["sample_rate"] == 16000
        assert info["channels"] == 1
        assert "pcm_s16le" in info["codec"]
