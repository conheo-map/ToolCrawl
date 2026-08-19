from pathlib import Path
from processors.vocal_separator import VocalSeparator, is_demucs_available

def test_vocal_separator_init():
    sep = VocalSeparator()
    # Check property
    assert isinstance(sep.available, bool)
    assert sep.available is True  # Spectral engine is active via librosa + noisereduce

def test_vocal_separator_missing_file(tmp_path: Path):
    sep = VocalSeparator()
    non_existent = tmp_path / "does_not_exist.wav"
    # Should safely return False
    assert sep.separate(non_existent) is False
