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
        "cơ mà", "hẳn là", "ôi giời", "nhá", "nhờ", "luôn á", "đấy nhé", "thế à",
    },
    "southern": {
        "hén", "nhen", "nghen", "hen", "hông", "thiệt", "dữ dằn", "bậy bạ", "dữ vậy",
        "dạ", "chèn ơi", "trời đất ơi", "bông hoa", "ly nước", "trái cây", "trễ rồi",
        "con heo", "trái bắp", "cây dù", "quá trời", "nhậu", "bữa nay", "vầy nè",
        "xỉu", "cơm tấm", "hủ tiếu", "bánh mì sài gòn", "mấy bà", "mấy ní", "tui",
        "trển", "bển", "trỏng", "hổng", "bự", "bận đồ", "dợ", "dzậy", "hén",
    },
    "central": {
        "chi rứa", "mô tê", "răng rứa", "răng hè", "mần chi", "bầy tui", "chộ không",
        "ưng bụng", "mắc cỡ", "trỏng", "ngoải", "choa", "mệ", "mì quảng", "bún bò huế",
        "cao lầu", "bánh bột lọc", "nem lụi", "mô", "tê", "răng", "rứa", "chi",
        "nớ", "ni", "hè", "ri", "trốc", "rơm", "tau", "mi",
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
        # 1. Manual Override
        if forced_region and forced_region.lower() in {"northern", "southern", "central", "mixed"}:
            return forced_region.lower()

        # 2. Check Known Channels Knowledge Base
        ch_clean = _normalize(channel_name).strip()
        for k_channel, k_region in KNOWN_CHANNELS.items():
            if k_channel in ch_clean or ch_clean.startswith(k_channel.lstrip("@")):
                logger.debug(f"[RegionClassifier] Channel matched '{k_channel}' -> {k_region}")
                return k_region

        # 3. Weighted Scoring từ Tiêu đề & Mô tả
        full_text = f"{title} {description} {channel_name}"
        scores = cls._calculate_scores(full_text)

        # Kiểm tra độ tự tin của điểm text
        top_region, top_score, is_confident = cls._eval_scores(scores)
        if is_confident:
            return top_region

        # 4. Whisper AI: Phiên âm 10s audio thực tế khi text không đủ tự tin
        if audio_path and Path(audio_path).exists():
            transcription = cls._transcribe_audio_snippet(Path(audio_path))
            if transcription:
                # Cộng thêm điểm từ lời nói thực tế
                audio_scores = cls._calculate_scores(transcription)
                for reg in scores:
                    scores[reg] += audio_scores[reg] * 2.0  # Lời nói nhân đôi trọng số
                top_region, top_score, _ = cls._eval_scores(scores)
                if top_score > 0:
                    return top_region

        return top_region if top_score > 0 else "mixed"

    @classmethod
    def _calculate_scores(cls, text: str) -> dict[str, float]:
        norm = _normalize(text)
        scores = {"northern": 0.0, "southern": 0.0, "central": 0.0}

        # Tính điểm Ngữ khí từ (5.0 điểm / từ)
        for region, kw_set in DIALECT_HIGH_WEIGHT.items():
            for kw in kw_set:
                if re.search(r"\b" + re.escape(kw) + r"\b", norm):
                    scores[region] += 5.0

        # Tính điểm Địa danh (1.5 điểm / từ)
        for region, kw_set in GEOGRAPHIC_WEIGHT.items():
            for kw in kw_set:
                if kw in norm:
                    scores[region] += 1.5

        return scores

    @classmethod
    def _eval_scores(cls, scores: dict[str, float]) -> tuple[str, float, bool]:
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_region, top_score = sorted_scores[0]
        second_region, second_score = sorted_scores[1]

        if top_score == 0:
            return "mixed", 0.0, False

        # Tự tin nếu điểm vượt trội so với vị trí thứ 2
        is_confident = (top_score >= 5.0 and (top_score - second_score) >= 3.0)
        return top_region, top_score, is_confident

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
