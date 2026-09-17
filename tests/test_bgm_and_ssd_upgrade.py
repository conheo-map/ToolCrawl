from pathlib import Path
import pytest
from config import get_quarantine_dir, PROJECT_ROOT
from processors.music_detector import MusicDetector
from processors.synthetic_speech_detector import SyntheticSpeechDetector
from processors.aed_prefilter import AudioEventPreFilter
from processors.vad_slicer import VadSlicer


def test_get_quarantine_dir():
    # Test specific crawl dates in Week1, Week2, etc.
    q_dir_aug20 = get_quarantine_dir("2026-08-20")
    assert "Week1" in str(q_dir_aug20)
    assert "2026-08-20" in str(q_dir_aug20)
    assert q_dir_aug20.name == "quarantine"

    q_dir_aug24 = get_quarantine_dir("2026-08-24")
    assert "Week2" in str(q_dir_aug24)
    assert "2026-08-24" in str(q_dir_aug24)


def test_synthetic_speech_detector_init():
    ssd = SyntheticSpeechDetector()
    assert ssd is not None
    prob, tag = ssd.analyze(Path("non_existent.wav"))
    assert prob == 0.0
    assert tag == "real"


def test_aed_prefilter_init():
    aed = AudioEventPreFilter()
    assert aed is not None
    res = aed.predict_events(Path("non_existent.wav"))
    assert "music_prob" in res
    assert "speech_prob" in res


def test_vad_slicer_init():
    slicer = VadSlicer()
    assert slicer is not None
    assert hasattr(slicer, "slice_audio")
