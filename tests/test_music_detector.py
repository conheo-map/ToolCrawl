import subprocess
from pathlib import Path
from processors.music_detector import MusicDetector
from config import QUARANTINE_DIR

def test_music_detector_metadata():
    md = MusicDetector()

    # Metadata test for original sound
    meta_original = {
        "platform": "tiktok",
        "platform_meta": {"music_is_original": True}
    }
    assert md.is_music(Path("dummy.wav"), meta_original) is False

    # Metadata test for non-original music track
    meta_music = {
        "platform": "tiktok",
        "platform_meta": {"music_is_original": False},
        "_track": "Son Tung MTP - Chung Ta Cua Tuong Lai"
    }
    assert md.is_music(Path("dummy.wav"), meta_music) is True

def test_music_detector_quarantine(tmp_path: Path):
    md = MusicDetector()
    fake_audio = tmp_path / "test_music.wav"
    fake_audio.write_bytes(b"RIFF....WAVEfmt ....")

    meta_music = {
        "platform": "tiktok",
        "platform_meta": {"music_is_original": False},
        "_track": "Hit Song 2026"
    }

    rejected = md.process(fake_audio, meta_music)
    assert rejected is True
    # The file should be quarantined
    quarantine_file = QUARANTINE_DIR / "test_music.wav"
    assert quarantine_file.exists()

    # Clean up test quarantine file
    quarantine_file.unlink(missing_ok=True)
