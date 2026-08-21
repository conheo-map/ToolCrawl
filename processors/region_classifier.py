"""
processors/region_classifier.py — Phân loại phương ngữ 4 miền chuẩn xác (High-Precision Regional Dialect Classifier).
Gán 1 trong 4 nhãn theo chuẩn ASR: "northern", "southern", "central", "mixed".

Kiến trúc Hybrid 4 Tầng:
  1. CLI/Config Override: Khi truyền cờ --region (northern/southern/central/mixed).
  2. Tri thức Kênh (Curated Channel Intelligence): Nhận diện các đài truyền hình & kênh lớn.
  3. Weighted Tone & Dialect Scoring: Trọng số ngữ khí từ (5.0x) vs Địa danh (1.5x).
  4. Whisper AI Speech Transcription: Phiên âm 10-15s giọng đọc audio thực tế khi không chắc chắn.
"""

import re
import unicodedata
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("region_classifier")

# ─────────────────────────────────────────────
# 1. BẢNG TRI THỨC KÊNH CHÍNH THỐNG
# ─────────────────────────────────────────────
KNOWN_CHANNELS = {
    # Miền Bắc (Trường quay Hà Nội, Đài TH, Giáo dục phía Bắc)
    "@vtv24news": "northern",
    "@dantri.com.vn": "northern",
    "@vnexpress.official": "northern",
    "@hocmai.vn": "northern",
    "@onluyen.vn": "northern",
    "@tuyensinh247.com": "northern",
    "@kienthuc.thuvi": "northern",
    "@vtctintuc": "northern",
    "@hanoitv": "northern",
    "@vtv1": "northern",
    "@vtv3": "northern",
    "@truyenhinhvov": "northern",
    
    # Miền Nam (TP.HCM & Miền Tây)
    "@tuoitreonline": "southern",
    "@thanhnien.official": "southern",
    "@saigontv": "southern",
    "@htv9": "southern",
    "@htv7": "southern",
    "@plo.vn": "southern",
    "@voh.com.vn": "southern",
    "@kenh14official": "southern",
    "@review.mientay": "southern",
    "@khoai.lang.thang": "southern",
    
    # Miền Trung & Tây Nguyên
    "@danangtv": "central",
    "@truyenhinhnghean": "central",
    "@thvl": "southern",
    "@vtv8": "central",
    "@reviewhue": "central",
    "@danang_oi": "central",
}

# ─────────────────────────────────────────────
# 2. BỘ TỪ KHÓA & TRỌNG SỐ PHƯƠNG NGỮ (WEIGHTED TONE)
# ─────────────────────────────────────────────

# Ngữ khí từ, từ xưng hô, thói quen phát âm đặc trưng (TRỌNG SỐ CAO: 5.0)
DIALECT_HIGH_WEIGHT = {
    "northern": {
        "nhé", "nhỉ", "ạ", "thế này", "đâu đấy", "buổi sáng", "xe máy", "bát cơm",
        "hoa quả", "muộn rồi", "con lợn", "cây ngô", "chiếc ô", "chứ lị", "giời ạ",
        "chuẩn đét", "phở hà nội", "bún chả", "trà đá vỉa hè", "đằng ấy", "bảo này",
        "cơ mà", "hẳn là", "ôi giời", "nhá", "nhờ", "đấy nhé", "thế à", "thế nhỉ",
        "đậu phụ", "dưa chuột", "mận hà nội", "nghìn", "nghìn đồng", "đỗ xe", "rẽ trái",
        "rẽ phải", "ngõ", "hầm", "bảo sao", "bảo là", "chứ lại", "thế hả", "gớm", "khiếp",
    },
    "southern": {
        "hén", "nhen", "nghen", "hen", "hông", "thiệt", "dữ dằn", "bậy bạ", "dữ vậy",
        "chèn ơi", "trời đất ơi", "bông hoa", "ly nước", "trái cây", "trễ rồi",
        "con heo", "trái bắp", "cây dù", "quá trời", "nhậu", "bữa nay", "vầy nè",
        "xỉu", "cơm tấm", "hủ tiếu", "bánh mì sài gòn", "mấy bà", "mấy ní", "tui",
        "trển", "bển", "trỏng", "hổng", "bự", "bận đồ", "dợ", "dzậy", "mắc cười",
        "mắc mệt", "quá xá", "dễ sợ", "cà phê sữa đá", "hổm rày", "bữa hổm", "quẹo",
        "hẻm", "ngàn", "ngàn đồng", "đậu xe", "dưa leo", "thơm", "khóm", "dòm", "quăng", "lụm",
    },
    "central": {
        "chi rứa", "mô tê", "răng rứa", "răng hè", "mần chi", "bầy tui", "chộ không",
        "ưng bụng", "mắc cỡ", "trỏng", "ngoải", "choa", "mệ", "mì quảng", "bún bò huế",
        "cao lầu", "bánh bột lọc", "nem lụi", "mô", "tê", "răng", "rứa", "chi",
        "nớ", "ni", "hè", "ri", "trốc", "rơm", "tau", "mi", "bầy bay", "o", "bọ",
        "chú mi", "mần", "trút", "đọi", "rú", "trửa", "bổ", "nỏ", "nỏ có", "mô có", "chi mô",
    },
}

# Địa danh hành chính (TRỌNG SỐ TRUNG BÌNH: 1.5)
GEOGRAPHIC_WEIGHT = {
    "northern": {
        "hà nội", "ha noi", "hanoi", "hải phòng", "quảng ninh", "hải dương", "hưng yên",
        "bắc ninh", "bắc giang", "lạng sơn", "cao bằng", "thái nguyên", "tuyên quang",
        "lào cai", "yên bái", "hà giang", "điện biên", "sơn la", "hòa bình", "phú thọ",
        "vĩnh phúc", "hà nam", "nam định", "thái bình", "ninh bình", "sơn tây",
    },
    "southern": {
        "sài gòn", "sai gon", "saigon", "tp hcm", "tphcm", "hồ chí minh", "bình dương",
        "đồng nai", "vũng tàu", "tây ninh", "bình phước", "long an", "tiền giang",
        "bến tre", "trà vinh", "vĩnh long", "đồng tháp", "an giang", "kiên giang",
        "cần thơ", "hậu giang", "sóc trăng", "bạc liêu", "cà mau", "miền tây",
    },
    "central": {
        "thanh hóa", "nghệ an", "hà tĩnh", "quảng bình", "quảng trị", "thừa thiên huế",
        "huế", "đà nẵng", "quảng nam", "quảng ngãi", "bình định", "phú yên",
        "khánh hòa", "nha trang", "ninh thuận", "bình thuận", "kon tum", "gia lai",
        "đắk lắk", "đắk nông", "lâm đồng", "đà lạt", "quy nhơn", "hội an", "vinh",
    },
}


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFC", text)
    return text


class RegionClassifier:
    """
    Bộ phân loại phương ngữ 4 miền tiếng Việt (Northern / Southern / Central / Mixed)
    kết hợp Channel Mapping + Weighted Lexicon + Whisper AI Speech Transcription.
    """

    _whisper_model = None

    @classmethod
    def _get_whisper_model(cls):
        """Khởi tạo WhisperModel một lần duy nhất (lazy loading)."""
        if cls._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                cls._whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
                logger.info("[RegionClassifier] faster-whisper tiny model initialized for acoustic verification")
            except Exception as exc:
                logger.debug(f"[RegionClassifier] faster-whisper not available: {exc}")
                cls._whisper_model = False
        return cls._whisper_model

    @classmethod
    def classify(
        cls,
        title: str = "",
        description: str = "",
        channel_name: str = "",
        audio_path: Path | None = None,
        forced_region: str | None = None,
    ) -> str:
        """
        Trả về 1 trong 4 nhãn chuẩn: "northern", "southern", "central", "mixed".
        """
        # 1. Manual CLI Override (Cao nhất khi người dùng chỉ định rõ)
        if forced_region and forced_region.lower() in {"northern", "southern", "central", "mixed"}:
            return forced_region.lower()

        scores = {"northern": 0.0, "southern": 0.0, "central": 0.0}

        # 2. Tri thức Kênh Nguồn (Đóng vai trò Prior Bias +3.0 điểm, không khóa cứng tuyệt đối)
        ch_clean = _normalize(channel_name).strip()
        for k_channel, k_region in KNOWN_CHANNELS.items():
            if k_channel in ch_clean or ch_clean.startswith(k_channel.lstrip("@")):
                scores[k_region] += 3.0  # Điểm nền tảng từ kênh
                break

        # 3. Phân tích Từ vựng & Ngữ khí từ Tiêu đề + Mô tả
        text_scores = cls._calculate_scores(f"{title} {description}")
        for reg in scores:
            scores[reg] += text_scores[reg]

        # 4. Whisper AI: Lắng nghe giọng nói thực tế từ Audio (Độ ưu tiên cao nhất)
        if audio_path and Path(audio_path).exists():
            transcription = cls._transcribe_audio_snippet(Path(audio_path))
            if transcription:
                audio_scores = cls._calculate_scores(transcription)
                # Lời nói thực tế mang trọng số tối thượng (Nhân 3.0)
                for reg in scores:
                    scores[reg] += audio_scores[reg] * 3.0

        # 5. Đánh giá & Phát hiện Video Đa Giọng (Mixed / Multi-speaker Detection)
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_reg, top_sc = sorted_scores[0]
        second_reg, second_sc = sorted_scores[1]

        # Trường hợp 1: Không có tín hiệu đặc trưng nào -> gán mixed
        if top_sc == 0:
            return "mixed"

        # Trường hợp 2: Phát hiện Đa giọng / Đan xen phỏng vấn (Mixed)
        # Nếu điểm số giữa miền thứ 1 và miền thứ 2 chênh lệch không nhiều (second_sc >= 45% top_sc)
        if second_sc >= 4.0 and (second_sc / top_sc) >= 0.45:
            logger.debug(f"[RegionClassifier] Multi-speaker / balanced dialect detected: {scores} -> mixed")
            return "mixed"

        # Trường hợp 3: Một miền chiếm ưu thế vượt trội rõ ràng
        if top_sc >= 4.0 and (top_sc - second_sc) >= 2.5:
            return top_reg

        return top_reg if top_sc > 0 else "mixed"

    @classmethod
    def _calculate_scores(cls, text: str) -> dict[str, float]:
        norm = _normalize(text)
        scores = {"northern": 0.0, "southern": 0.0, "central": 0.0}

        # Tính điểm Khẩu ngữ & Ngữ khí đặc trưng (6.0 điểm / từ) — Ưu tiên cao nhất
        for region, kw_set in DIALECT_HIGH_WEIGHT.items():
            for kw in kw_set:
                if re.search(r"\b" + re.escape(kw) + r"\b", norm):
                    scores[region] += 6.0

        # Tính điểm Địa danh (1.0 điểm / từ) — Tránh bị đánh lừa bởi hashtag câu view
        for region, kw_set in GEOGRAPHIC_WEIGHT.items():
            for kw in kw_set:
                if kw in norm:
                    scores[region] += 1.0

        return scores

    @classmethod
    def _transcribe_audio_snippet(cls, audio_path: Path) -> str:
        model = cls._get_whisper_model()
        if not model or model is False:
            return ""

        try:
            segments, _ = model.transcribe(
                str(audio_path),
                language="vi",
                vad_filter=True,
                max_new_tokens=40,
            )
            text = " ".join([seg.text for seg in segments])
            return text
        except Exception as exc:
            logger.debug(f"[RegionClassifier] Whisper snippet error for {audio_path.name}: {exc}")
            return ""
