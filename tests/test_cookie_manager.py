"""
tests/test_cookie_manager.py — Unit test cho CookieManager (Cookie Rotation).
"""

from pathlib import Path
from utils.cookie_manager import CookieManager

def test_cookie_manager_single_file(tmp_path: Path):
    c1 = tmp_path / "cookie1.txt"
    c1.write_text("# Netscape HTTP Cookie File\n.tiktok.com TRUE / FALSE 0 session 123", encoding="utf-8")
    
    cm = CookieManager(cookie_input=c1, platform="tiktok")
    assert cm.count() == 1
    assert cm.get_cookie() == c1

def test_cookie_manager_folder_rotation(tmp_path: Path):
    c1 = tmp_path / "tiktok_01.txt"
    c1.write_text("cookie1", encoding="utf-8")
    c2 = tmp_path / "tiktok_02.txt"
    c2.write_text("cookie2", encoding="utf-8")
    c3 = tmp_path / "tiktok_03.txt"
    c3.write_text("cookie3", encoding="utf-8")

    cm = CookieManager(cookie_input=tmp_path, platform="tiktok")
    assert cm.count() == 3

    # Check Round-Robin rotation
    used = [cm.get_cookie().name for _ in range(6)]
    assert used == ["tiktok_01.txt", "tiktok_02.txt", "tiktok_03.txt", "tiktok_01.txt", "tiktok_02.txt", "tiktok_03.txt"]

def test_cookie_manager_blacklist(tmp_path: Path):
    c1 = tmp_path / "tiktok_01.txt"
    c1.write_text("cookie1", encoding="utf-8")
    c2 = tmp_path / "tiktok_02.txt"
    c2.write_text("cookie2", encoding="utf-8")

    cm = CookieManager(cookie_input=tmp_path, platform="tiktok")
    assert cm.count() == 2

    # Blacklist c1
    cm.mark_bad(c1)
    assert cm.count() == 1
    assert cm.get_cookie() == c2
    assert cm.get_cookie() == c2
