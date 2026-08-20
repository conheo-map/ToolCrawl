"""
processors/region_classifier.py — Phân loại vùng miền (Dialect / Region Classifier)
Gán 1 trong 4 nhãn theo chuẩn ASR: "northern", "southern", "central", "mixed".
"""

import re
import unicodedata
from utils.logger import get_logger

logger = get_logger("region_classifier")

# ─────────────────────────────────────────────
# Bộ từ khóa nhận diện phương ngữ & địa danh
# ─────────────────────────────────────────────

NORTHERN_KEYWORDS = {
    # Địa danh Miền Bắc
    "hà nội", "ha noi", "hanoi", "hải phòng", "hai phong", "quảng ninh", "quang ninh",
    "hải dương", "hưng yên", "bắc ninh", "bắc giang", "lạng sơn", "cao bằng",
    "bắc kạn", "thái nguyên", "tuyên quang", "lào cai", "yên bái", "hà giang",
    "điện biên", "lai châu", "sơn la", "hòa bình", "phú thọ", "vĩnh phúc",
    "hà nam", "nam định", "thái bình", "ninh bình", "sơn tây", "ba đình",
    "hoàn kiếm", "tây hồ", "cầu giấy", "đống đa", "hai bà trưng", "thanh xuân",
    "hoàng mai", "long biên", "nam từ liêm", "bắc từ liêm", "hà đông",
    # Từ ngữ / Phương ngữ Bắc
    "nhé", "nhỉ", "ạ", "thế à", "đâu đấy", "buổi sáng", "xe máy", "bát cơm",
    "hoa quả", "muộn rồi", "con lợn", "bắp ngô", "cây ngô", "chiếc ô", "vào đây",
    "chứ lị", "giời ạ", "chuẩn đét", "phở hà nội", "bún chả", "trà đá vỉa hè",
    # Hashtags
    "#hanoi", "#mienbac", "#nguoimienbac", "#giongbac", "#reviewhanoi", "#amthuchanoi",
}

SOUTHERN_KEYWORDS = {
    # Địa danh Miền Nam & Miền Tây
    "sài gòn", "sai gon", "saigon", "tp hcm", "tphcm", "hồ chí minh", "ho chi minh",
    "bình dương", "đồng nai", "bà rịa", "vũng tàu", "tây ninh", "bình phước",
    "long an", "tiền giang", "bến tre", "trà vinh", "vĩnh long", "đồng tháp",
    "an giang", "kiên giang", "cần thơ", "hậu giang", "sóc trăng", "bạc liêu",
    "cà mau", "miền tây", "sông nước", "thủ đức", "gò vấp", "bình thạnh",
    "tân bình", "quận 1", "quận 3", "quận 7", "quận 10", "quận 12",
    # Từ ngữ / Phương ngữ Nam
    "hén", "nhen", "nghen", "hen", "hông", "thiệt", "dữ dằn", "bậy bạ",
    "dữ vậy", "dạ", "chèn ơi", "trời đất ơi", "bông hoa", "ly nước",
    "trái cây", "trễ rồi", "con heo", "trái bắp", "cây dù", "quá trời",
    "nhậu", "bữa nay", "vầy nè", "xỉu", "cơm tấm", "hủ tiếu", "bánh mì sài gòn",
    # Hashtags
    "#saigon", "#mientay", "#nguoimientay", "#giongnam", "#reviewsaigon", "#tphcm",
}

CENTRAL_KEYWORDS = {
    # Địa danh Miền Trung & Tây Nguyên
    "thanh hóa", "nghệ an", "hà tĩnh", "quảng bình", "quảng trị", "thừa thiên huế",
    "huế", "đà nẵng", "da nang", "quảng nam", "quảng ngãi", "bình định",
    "phú yên", "khánh hòa", "nha trang", "ninh thuận", "phan rang", "bình thuận",
    "phan thiết", "kon tum", "gia lai", "đắk lắk", "đắk nông", "lâm đồng",
    "đà lạt", "quy nhơn", "hội an", "sông hàn", "cầu rồng", "vinh",
    # Từ ngữ / Phương ngữ Trung
    "chi rứa", "mô tê", "răng rứa", "răng hè", "mần chi", "bầy tui", "chộ không",
    "ưng bụng", "mắc cỡ", "trỏng", "ngoải", "choa", "mệ", "mì quảng", "bún bò huế",
    "cao lầu", "bánh bột lọc", "nem lụi",
    # Hashtags
    "#mientrung", "#danang", "#hue", "#nghetinh", "#giongtrung", "#reviewdanang",
}


def _normalize(text: str) -> str:
    """Chuẩn hóa text về lowercase và bỏ dấu phụ trùng lặp."""
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFC", text)
    return text


class RegionClassifier:
    """
    Phân loại vùng miền tiếng Việt (Northern / Southern / Central / Mixed)
    dựa trên tiêu đề, mô tả, hashtag, và từ khóa phương ngữ.
    """

    @staticmethod
    def classify(
        title: str = "",
        description: str = "",
        channel_name: str = "",
        forced_region: str | None = None,
    ) -> str:
        """
        Trả về 1 trong 4 nhãn chuẩn: "northern", "southern", "central", "mixed".
        """
        # Nếu có override cố định từ CLI/Config
        if forced_region and forced_region.lower() in {"northern", "southern", "central", "mixed"}:
            return forced_region.lower()

        full_text = f"{title} {description} {channel_name}"
        normalized = _normalize(full_text)

        if not normalized.strip():
            return "mixed"

        # Tính điểm cho từng miền
        score_north = sum(1 for kw in NORTHERN_KEYWORDS if kw in normalized)
        score_south = sum(1 for kw in SOUTHERN_KEYWORDS if kw in normalized)
        score_central = sum(1 for kw in CENTRAL_KEYWORDS if kw in normalized)

        scores = {
            "northern": score_north,
            "southern": score_south,
            "central": score_central,
        }

        max_region = max(scores, key=scores.get)
        max_score = scores[max_region]

        # Nếu không có từ khóa nào xuất hiện -> mixed
        if max_score == 0:
            return "mixed"

        # Kiểm tra xem có bị xung đột nhiều miền ngang điểm không
        sorted_scores = sorted(scores.values(), reverse=True)
        if sorted_scores[0] == sorted_scores[1] and sorted_scores[0] > 0:
            return "mixed"

        logger.debug(
            f"Region classification: N={score_north}, S={score_south}, C={score_central} -> {max_region}"
        )
        return max_region
