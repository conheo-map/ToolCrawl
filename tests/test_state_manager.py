from pathlib import Path
from storage.state_manager import StateManager

def test_state_manager(tmp_path: Path):
    ckpt_file = tmp_path / "test_checkpoint.json"
    sm = StateManager(platform="tiktok", checkpoint_file=ckpt_file)
    url = "https://www.tiktok.com/@user/video/7412345678901234567"

    assert not sm.is_done(url)
    sm.mark_done(url)
    assert sm.is_done(url)

    failed_url = "https://www.tiktok.com/@user/video/99999"
    sm.add_failed(failed_url, "Network error")
    failed = sm.load_failed()
    assert failed_url in failed
    assert failed[failed_url] == "Network error"

    # Reload from same checkpoint file
    sm2 = StateManager(platform="tiktok", checkpoint_file=ckpt_file)
    assert sm2.is_done(url)
    assert sm2.load_failed()[failed_url] == "Network error"
