"""
tests/test_region_classifier.py — Kiểm thử phân loại vùng miền tiếng Việt (ASR Region Classifier).
"""

from processors.region_classifier import RegionClassifier


def test_northern_classification():
    # Test Hà Nội, phương ngữ Bắc
    title = "Review quán bún chả Hà Nội phố cổ siêu ngon"
    desc = "Hôm nay dẫn các bạn đi ăn phở và uống trà đá vỉa hè nhé #hanoi #mienbac"
    region = RegionClassifier.classify(title=title, description=desc)
    assert region == "northern"


def test_southern_classification():
    # Test Sài Gòn, phương ngữ Nam
    title = "Đi ăn cơm tấm Sài Gòn cùng tui nè"
    desc = "Bữa nay trời mưa dữ dội quá trời, ghé quán ăn hủ tiếu nghen #saigon #mientay"
    region = RegionClassifier.classify(title=title, description=desc)
    assert region == "southern"


def test_central_classification():
    # Test Đà Nẵng / Huế, phương ngữ Trung
    title = "Ăn mì quảng Đà Nẵng ở cầu rồng"
    desc = "Ở đây có chi mô tê mà ngon rứa hè #danang #mientrung"
    region = RegionClassifier.classify(title=title, description=desc)
    assert region == "central"


def test_mixed_classification():
    # Test không có từ khóa địa phương rõ ràng
    title = "Chia sẻ kiến thức công nghệ và lập trình máy tính"
    desc = "Video hướng dẫn cài đặt phần mềm mới nhất 2026."
    region = RegionClassifier.classify(title=title, description=desc)
    assert region == "mixed"


def test_forced_region_override():
    # Test cưỡng bức nhãn
    region = RegionClassifier.classify(title="Hà Nội", forced_region="southern")
    assert region == "southern"
