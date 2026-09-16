"""
processors/content_guard.py — Lọc và phân loại nội dung cho tập huấn luyện ASR.

TIÊU CHÍ ĐẶC TẢ CỦA CÔNG TY:
  [NHÓM MỤC TIÊU CẦN GIỮ LẠI -> ACTION: ACCEPT]
  1. TIN_TUC_THOI_SU: Thời sự, tin tức, bản tin, kinh tế, xã hội, giao thông, thời tiết.
  2. PHAP_LUAT: Pháp luật, tòa án, quy định pháp lý, xét xử, tư vấn luật.
  3. HOC_ONLINE_GIAO_DUC: Bài giảng, luyện thi, giải đề, học tiếng, kỹ năng kiến thức.
  4. HOI_THOAI_DOI_SONG: Giao tiếp tự nhiên đời thường, nấu ăn, du lịch, chia sẻ cuộc sống.

  [NHÓM RÁC CẦN LOẠI BỎ -> ACTION: REJECT]
  1. QUANG_CAO_TIEP_THI: Chốt đơn, mua ngay, link bio, affiliate, livestream bán hàng, freeship.
  2. NHAC_TREND_VO_NGHIA: Nhạc trend biến hình, nhép môi, nhảy nhót, không có lời thoại tự nhiên.
  3. SPAM_CO_BAC_DOC_HAI: Cá cược, tài xỉu, kèo bóng đá, link telegram lừa đảo.
  4. TRANSCRIPT_RONG_HOAC_VO_NGHIA: < 3 từ, âm thanh không có tiếng nói rõ nghĩa.
"""

import re
from dataclasses import dataclass
from typing import Optional
from utils.logger import get_logger

logger = get_logger("content_guard")


@dataclass
class ContentDecision:
    """Kết quả phân loại nội dung."""
    category: str           # Chủ đề chính
    confidence: float       # Độ tin cậy (0.0 - 1.0)
    action: str             # "ACCEPT" | "REJECT" | "FLAG"
    reason: str             # Lý do cụ thể
    scores: dict = None     # Chi tiết điểm từng category


class ContentGuard:
    """
    Bộ lọc nội dung thông minh tích hợp vào pipeline ASR.
    Bảo toàn các chủ đề: Tin tức, Pháp luật, Học online, Hội thoại đời sống.
    Loại bỏ: Quảng cáo, Rác trend lồng nhạc vô nghĩa, Cá cược lừa đảo.
    """

    # Danh mục mục tiêu cần GIỮ LẠI (ACCEPT)
    TARGET_CATEGORIES = {
        "TIN_TUC_THOI_SU",
        "PHAP_LUAT",
        "HOC_ONLINE_GIAO_DUC",
        "HOI_THOAI_DOI_SONG",
    }

    # Danh mục rác cần LOẠI BỎ (REJECT)
    REJECT_CATEGORIES = {
        "QUANG_CAO_TIEP_THI",
        "NHAC_TREND_VO_NGHIA",
        "SPAM_CO_BAC_DOC_HAI",
    }

    # 1. Từ khóa TIN TỨC & THỜI SỰ (GIỮ LẠI)
    NEWS_KEYWORDS = [
        ("thời sự", 2.0), ("tin tức", 2.0), ("bản tin", 2.0), ("phóng viên", 2.5),
        ("ghi nhận tại", 2.0), ("dự báo thời tiết", 2.5), ("bộ công an", 2.5),
        ("chính phủ", 1.5), ("thủ tướng", 1.5), ("quốc hội", 1.5),
        ("giá vàng", 1.5), ("xăng dầu", 1.5), ("chứng khoán", 2.0),
        ("vtv1", 3.0), ("vtv24", 3.0), ("vtc", 2.0), ("vov", 2.0),
        ("dân trí", 2.5), ("tuổi trẻ online", 2.5), ("vnexpress", 2.5),
        ("tin nóng", 2.0), ("tin mới", 1.5), ("hôm nay ghi nhận", 2.0),
        ("cứu nạn cứu hộ", 2.0), ("tai nạn giao thông", 2.0), ("cháy nổ", 1.5),
        ("khởi tố bị can", 3.0), ("bị can", 2.5), ("cơ quan điều tra", 2.5),
        ("kinh tế", 1.5), ("thị trường", 1.5), ("quốc tế", 1.5),
    ]

    # 2. Từ khóa PHÁP LUẬT (GIỮ LẠI)
    LAW_KEYWORDS = [
        ("điều này quy định", 3.0), ("theo quy định của pháp luật", 3.0),
        ("bộ luật hình sự", 3.0), ("bộ luật dân sự", 3.0),
        ("tòa án", 2.5), ("viện kiểm sát", 2.5), ("hội đồng xét xử", 3.0),
        ("bản án", 2.5), ("phán quyết", 2.5), ("xử phạt vi phạm", 2.5),
        ("điều khoản", 1.5), ("nghị định số", 2.5), ("thông tư số", 2.5),
        ("luật sư", 2.0), ("bị cáo", 2.5), ("bị hại", 2.0),
        ("hành vi vi phạm", 2.0), ("tội phạm", 2.0), ("luật giao thông", 2.0),
    ]

    # 3. Từ khóa HỌC ONLINE & LUYỆN THI (GIỮ LẠI)
    EDU_KEYWORDS = [
        ("bài giảng hôm nay", 3.0), ("giải đề", 2.5), ("luyện thi", 2.5),
        ("ôn thi thpt", 3.0), ("thi đại học", 2.5), ("đỗ nguyện vọng", 2.5),
        ("toán lớp", 2.5), ("vật lý lớp", 2.5), ("hóa học lớp", 2.5),
        ("ielts", 3.0), ("toeic", 3.0), ("học tiếng anh", 2.0),
        ("ngữ pháp tiếng", 2.5), ("từ vựng hôm nay", 2.5),
        ("learnontiktok", 3.0), ("studytok", 3.0), ("học phát âm", 2.0),
        ("giáo viên hướng dẫn", 2.5), ("học sinh chú ý", 2.5),
        ("phương pháp giải", 2.5), ("công thức tính", 2.5),
        ("kiến thức cần nhớ", 2.0), ("thầy cô", 1.5), ("bài tập về nhà", 2.0),
    ]

    # 4. Từ khóa QUẢNG CÁO & BÁN HÀNG (CẦN LOẠI BỎ)
    ADS_KEYWORDS = [
        ("mua ngay", 3.0), ("order ngay", 3.0), ("đặt hàng ngay", 3.0),
        ("ưu đãi chỉ hôm nay", 3.5), ("giảm giá sốc", 3.0), ("flash sale", 3.0),
        ("dm để được tư vấn", 3.5), ("inbox để được tư vấn", 3.5),
        ("link trong bio", 3.0), ("link bio", 2.5), ("mã giảm giá", 2.5),
        ("hoa hồng hấp dẫn", 3.0), ("affiliate", 2.5), ("cộng tác viên", 2.0),
        ("miễn phí ship", 2.5), ("freeship", 2.5), ("giao hàng toàn quốc", 2.0),
        ("chốt đơn", 3.0), ("giỏ hàng bên dưới", 3.5), ("bấm vào giỏ hàng", 3.5),
        ("combo siêu hời", 3.0), ("xả kho", 3.0),
    ]

    # 5. Từ khóa NHẠC TREND VÔ NGHĨA (CẦN LOẠI BỎ)
    JUNK_TREND_KEYWORDS = [
        ("remix", 2.5), ("biến hình", 3.0), ("trend tiktok", 2.5),
        ("lời bài hát", 2.5), ("nhạc chill", 2.5), ("nhạc lofi", 2.5),
        ("bài hát này", 2.0), ("nhạc nền", 2.0), ("nghe nhạc cùng", 2.5),
        ("speed up", 2.5), ("slowed", 2.5),
    ]

    # 6. Từ khóa CÁ CƯỢC & ĐỘC HẠI (CẦN LOẠI BỎ)
    GAMBLING_KEYWORDS = [
        ("tài xỉu", 4.0), ("kubet", 4.0), ("sunwin", 4.0), ("kèo bóng đá", 3.5),
        ("nhóm kéo telegram", 4.0), ("nạp rút 1 1", 3.5), ("nhận code tân thủ", 4.0),
    ]

    REJECT_THRESHOLD = 3.5

    def __init__(self, reject_threshold: float = None) -> None:
        self._threshold = reject_threshold or self.REJECT_THRESHOLD

    def _vn_score(self, text: str, keyword_list: list) -> float:
        """Vietnamese-aware keyword scoring. Không dùng \b để hỗ trợ tiếng Việt có dấu."""
        text_lower = text.lower().strip()
        score = 0.0
        for kw, weight in keyword_list:
            pattern = r'(?:(?<=\s)|(?<=^))' + re.escape(kw) + r'(?=\s|[.,!?;:"]|$)'
            count = len(re.findall(pattern, text_lower))
            if count > 0:
                score += weight * min(count, 2)
        return score

    def classify(self, transcript: str, metadata: Optional[dict] = None) -> ContentDecision:
        """
        Phân loại transcript và trả về quyết định:
          - ACCEPT: Tin tức, Pháp luật, Học online, Hội thoại đời sống.
          - REJECT: Quảng cáo bán hàng, Nhạc trend vô nghĩa, Cá cược.
        """
        # Kiểm tra độ dài: nếu quá ngắn (< 3 từ) -> REJECT vì không đủ chất lượng ASR
        words = transcript.strip().split() if transcript else []
        if len(words) < 3:
            return ContentDecision(
                category="TRANSCRIPT_QUA_NGAN",
                confidence=1.0,
                action="REJECT",
                reason=f"Transcript quá ngắn ({len(words)} từ < 3 từ), không đạt chuẩn ASR",
                scores={},
            )

        combined_text = transcript
        if metadata:
            title = metadata.get("title") or metadata.get("description") or ""
            hashtags = " ".join(metadata.get("hashtags", []))
            combined_text = f"{title} {hashtags} {transcript} {title} {hashtags}"

        # 1. Tính điểm các nhóm RÁC (Cần ưu tiên phát hiện để loại bỏ)
        ads_score = self._vn_score(combined_text, self.ADS_KEYWORDS)
        junk_score = self._vn_score(combined_text, self.JUNK_TREND_KEYWORDS)
        gambling_score = self._vn_score(combined_text, self.GAMBLING_KEYWORDS)

        if gambling_score >= 3.5:
            return ContentDecision(
                category="SPAM_CO_BAC_DOC_HAI",
                confidence=0.95,
                action="REJECT",
                reason=f"Phát hiện nội dung cá cược/lừa đảo (score={gambling_score:.1f})",
                scores={"gambling": gambling_score},
            )

        if ads_score >= self._threshold:
            return ContentDecision(
                category="QUANG_CAO_TIEP_THI",
                confidence=min(1.0, ads_score / (self._threshold * 1.5)),
                action="REJECT",
                reason=f"Phát hiện quảng cáo / tiếp thị / bán hàng (score={ads_score:.1f})",
                scores={"ads": ads_score},
            )

        if junk_score >= self._threshold:
            return ContentDecision(
                category="NHAC_TREND_VO_NGHIA",
                confidence=min(1.0, junk_score / (self._threshold * 1.5)),
                action="REJECT",
                reason=f"Phát hiện nội dung nhạc trend / biến hình không có lời đàm thoại (score={junk_score:.1f})",
                scores={"junk": junk_score},
            )

        # 2. Tính điểm các nhóm MỤC TIÊU (Cần giữ lại)
        news_score = self._vn_score(combined_text, self.NEWS_KEYWORDS)
        law_score = self._vn_score(combined_text, self.LAW_KEYWORDS)
        edu_score = self._vn_score(combined_text, self.EDU_KEYWORDS)

        scores = {
            "TIN_TUC_THOI_SU": news_score,
            "PHAP_LUAT": law_score,
            "HOC_ONLINE_GIAO_DUC": edu_score,
        }
        best_target = max(scores, key=scores.get)
        best_target_score = scores[best_target]

        # Nếu đạt điểm nhận diện rõ ràng của 1 trong 3 nhóm mục tiêu chuyên sâu
        if best_target_score >= 2.0:
            return ContentDecision(
                category=best_target,
                confidence=min(1.0, 0.7 + best_target_score * 0.1),
                action="ACCEPT",
                reason=f"Nội dung chuẩn ASR mục tiêu: {best_target} (score={best_target_score:.1f})",
                scores=scores,
            )

        # 3. Nếu không dính rác và không thuộc nhóm tin/luật/học -> Hội thoại đời sống thực tế
        return ContentDecision(
            category="HOI_THOAI_DOI_SONG",
            confidence=0.85,
            action="ACCEPT",
            reason="Nội dung hội thoại & đời sống thực tế, đạt tiêu chuẩn ASR",
            scores=scores,
        )

    def is_acceptable(self, transcript: str, metadata: Optional[dict] = None) -> bool:
        return self.classify(transcript, metadata).action == "ACCEPT"