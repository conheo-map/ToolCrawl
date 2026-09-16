"""
utils/dialect_classifier.py — Bộ nhận diện vùng miền chuyên sâu (North, Central, South, Mixed)
DỰA HOÀN TOÀN TRÊN TỪ NGỮ ĐỊA PHƯƠNG VÀ GIỌNG ĐIỆU / NGỮ ÂM CỦA NGƯỜI NÓI (AUDIO & TRANSCRIPT).
TUYỆT ĐỐI KHÔNG DỰA VÀO TÊN KÊNH HAY TÁC GIẢ.
"""

import re
import numpy as np
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 1. HỆ THỐNG TỪ VỰNG PHƯƠNG NGỮ ĐẶC TRƯNG CÁC MIỀN
# ─────────────────────────────────────────────────────────────────────────────
CENTRAL_VOCAB = [
    "chi", "mô", "tê", "răng", "rứa", "ngái", "nớ", "trốc", "cươi", "nhút", "mi", "tau",
    "đoạn ni", "cái ni", "chộ", "ngó", "nỏ", "nỏ có", "mần chi", "mần răng", "bác hò",
    "xứ nghệ", "trốc cú", "nhủ", "hỉ", "đọi", "chộ", "nỏ biết", "om", "chấy", "trút",
    "bầy tui", "bầy bay", "nớ nớ", "răng hè", "mô hè", "rứa hè", "mần ăn", "đàng nớ",
    "gấy", "bổ", "đút", "nác", "khu", "troóc", "mệ", "chắt", "dừ", "nậy", "nhỏ thó"
]

SOUTH_VOCAB = [
    "hổng", "xỉn", "bự", "nhậu", "lẹ", "kìa", "nghen", "nè", "bảnh", "bồ", "má", "tía",
    "ba mẹ", "ổng", "bà đó", "nhen", "hén", "thiệt", "dữ dằn", "bực bội", "quá trời",
    "nhóc", "ghe", "miệt vườn", "bển", "trển", "trỏng", "ngoải", "bậy bạ", "quá xá",
    "sao dạ", "dạ thưa", "dữ ha", "hổng chịu", "hổng được", "chút xíu", "bữa nay",
    "mần ăn", "quá chừng", "hổng dám", "kỳ cục", "ngon lành", "ngủm", "rề rề", "cưng",
    "hổng có", "thiệt tình", "trời đất ơi", "bạc mạng", "chết queo", "nhí nhảnh", "xạo ke"
]

NORTH_VOCAB = [
    "nhỉ", "nhé", "thế à", "vâng", "ạ", "đây này", "cái gì cơ", "sao cơ", "thế này",
    "thế kia", "chứ lị", "được đấy", "hẳn hoi", "chả nhẽ", "thế nhé", "ối dồi ôi",
    "buồn cười", "làm sao cơ", "chứ sao", "chuẩn luôn", "cơ mà", "nào ngờ", "chứ lại",
    "thế ư", "ra phết", "thế thôi", "tí ti", "gớm", "khiếp", "vớ vẩn", "thôi xong"
]


def _analyze_audio_prosody(wav_path: Path | str | None) -> dict:
    """
    Phân tích đặc trưng ngữ âm, cao độ (Pitch/F0) và độ biến thiên giọng điệu từ audio.
    """
    if not wav_path or not Path(wav_path).exists():
        return {"pitch_std": 0.0, "pitch_mean": 0.0, "is_multispeaker": False}

    try:
        import soundfile as sf
        data, sr = sf.read(str(wav_path))
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        # Lấy tối đa 15 giây đầu để tính toán nhanh
        max_samples = min(len(data), sr * 15)
        segment = data[:max_samples]

        # Tính Zero Crossing Rate & Short-time Energy
        zcr = np.mean(np.abs(np.diff(np.sign(segment)))) / 2.0
        rms = np.sqrt(np.mean(segment**2))

        # Phân tích F0 thô bằng autocorrelation trên khung 40ms
        frame_len = int(sr * 0.04)
        hop_len = int(sr * 0.02)
        pitches = []

        for i in range(0, len(segment) - frame_len, hop_len * 4):
            frame = segment[i:i + frame_len]
            if np.max(np.abs(frame)) < 0.02:
                continue
            corr = np.correlate(frame, frame, mode='full')[frame_len - 1:]
            # Giới hạn tần số người nói 80Hz - 350Hz
            min_lag = int(sr / 350)
            max_lag = int(sr / 80)
            if len(corr) > max_lag:
                peak_lag = min_lag + np.argmax(corr[min_lag:max_lag])
                if corr[peak_lag] > 0.3 * corr[0]:
                    f0 = sr / peak_lag
                    pitches.append(f0)

        if len(pitches) >= 5:
            p_mean = float(np.mean(pitches))
            p_std = float(np.std(pitches))
            # Kiểm tra phân bố 2 cụm (đối thoại 2 người - Mixed)
            p_diff = np.percentile(pitches, 85) - np.percentile(pitches, 15)
            is_multispeaker = p_diff > 90.0 and len(pitches) > 15
            return {"pitch_std": p_std, "pitch_mean": p_mean, "is_multispeaker": is_multispeaker}
    except Exception:
        pass

    return {"pitch_std": 0.0, "pitch_mean": 0.0, "is_multispeaker": False}


def classify_region(text: str = "", wav_path: Path | str | None = None) -> str:
    """
    Nhận diện vùng miền chính xác dựa trên LỜI NÓI & NGỮ ÂM (Audio Prosody + Dialect Lexicon).
    Trả về 1 trong 4 nhãn chuẩn:
      - 'North'   (Giọng Bắc)
      - 'Central' (Giọng Trung)
      - 'South'   (Giọng Nam)
      - 'Mixed'   (Giọng hỗn hợp / Đa người nói)
    """
    full_text = f" {text.lower()} "

    # 1. Đếm điểm từ vựng phương ngữ
    central_hits = [w for w in CENTRAL_VOCAB if f" {w} " in full_text or re.search(r'\b' + re.escape(w) + r'\b', full_text)]
    south_hits = [w for w in SOUTH_VOCAB if f" {w} " in full_text or re.search(r'\b' + re.escape(w) + r'\b', full_text)]
    north_hits = [w for w in NORTH_VOCAB if f" {w} " in full_text or re.search(r'\b' + re.escape(w) + r'\b', full_text)]

    c_score = len(central_hits)
    s_score = len(south_hits)
    n_score = len(north_hits)

    # 2. Phân tích giọng điệu từ audio
    audio_feat = _analyze_audio_prosody(wav_path)

    # Nếu phát hiện âm thanh có nhiều người nói giọng điệu khác nhau
    if audio_feat["is_multispeaker"]:
        # Nếu xuất hiện từ ngữ của cả 2 miền khác nhau
        if (c_score > 0 and (s_score > 0 or n_score > 0)) or (s_score > 0 and n_score > 0):
            return "Mixed"

    # Nếu xuất hiện đồng thời từ ngữ của nhiều miền trong cùng 1 transcript
    if (c_score >= 1 and s_score >= 1) or (c_score >= 1 and n_score >= 1) or (s_score >= 2 and n_score >= 2):
        return "Mixed"

    # 3. Phân loại theo ưu tiên từ vựng phương ngữ đặc thù
    if c_score >= 1:
        return "Central"

    if s_score >= 1:
        # Ngữ điệu Nam có độ biến thiên F0 rộng hơn
        return "South"

    if n_score >= 1:
        return "North"

    # 4. Khi transcript trung tính (không có từ lóng đặc thù): Dùng đặc trưng ngữ âm / cao độ F0
    p_std = audio_feat["pitch_std"]
    if p_std >= 38.0:
        # Giọng điệu uốn lượn, lên bổng xuống trầm mạnh (đặc trưng ngữ điệu Nam Bộ)
        return "South"
    elif 0 < p_std <= 20.0 and audio_feat["pitch_mean"] < 170.0:
        # Âm vực phẳng, gắt, dốc (đặc trưng ngữ điệu miền Trung)
        return "Central"

    # Chuẩn phát thanh tiếng Việt mặc định
    return "North"
