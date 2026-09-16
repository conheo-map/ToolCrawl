"""
tools/qc_asr_specialist_evaluator.py — Hệ thống thẩm định âm thanh chuyên sâu 5 trụ cột ASR.
Chấm điểm cực kỳ khắt khe theo thang 10.0, phân loại chính xác:
  1. KEEP (Giữ lại): Đạt chuẩn ASR vàng, giữ trọn bản sắc ngữ âm
  2. RECRAWL (Cào lại): Nội dung giá trị nhưng bị lỗi tiền xử lý/cắt cụt/dính nhạc
  3. DELETE (Xóa đi): Rác, TTS bot, quảng cáo, nhạc tạp nham
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
import numpy as np
import soundfile as sf
from pathlib import Path
from collections import Counter

# Từ khóa địa phương quý hiếm
CENTRAL_DIALECT_LEXICON = {
    "chi", "mô", "tê", "răng", "rứa", "ngái", "nớ", "trốc", "cươi", "mi", "tau",
    "bọ", "mạ", "o", "dượng", "bựa", "nậy", "hun", "nhút", "trút", "nác", "khu",
    "nghệ an", "hà tĩnh", "quảng bình", "quảng trị", "huế", "nam đàn", "đô lương"
}

ADS_JUNK_LEXICON = {
    "giỏ hàng", "chốt đơn", "link bio", "mua ngay", "voucher", "freeship", "tiktok shop",
    "giảm giá", "sale sập sàn", "nhạc remix", "karaoke", "nhạc hoa lời việt", "cover"
}

TTS_KEYWORDS = {
    "chị google", "siri", "voice ai", "giọng đọc ai", "text to speech", "tts", "bot đọc"
}

def analyze_audio_pillars(wav_path: Path, transcript: str = "", metadata: dict = None):
    """
    Thẩm định toàn diện 1 file âm thanh theo 5 trụ cột ASR.
    Trả về: (score, decision, pillar_scores, details, reasons)
    """
    if metadata is None: metadata = {}
    details = {}
    reasons = []
    
    # ─────────────────────────────────────────────────────────────
    # ĐỌC VÀ PHÂN TÍCH TÍN HIỆU ÂM THANH
    # ─────────────────────────────────────────────────────────────
    try:
        data, sr = sf.read(str(wav_path), dtype="float32")
    except Exception as e:
        return 0.0, "DELETE", {}, {"error": str(e)}, ["File hỏng không đọc được"]

    if data.ndim > 1:
        data = np.mean(data, axis=1) # stereo to mono

    total_samples = len(data)
    duration = total_samples / sr
    details["duration"] = round(duration, 2)
    details["sample_rate"] = sr

    text_lower = (transcript + " " + metadata.get("title", "") + " " + metadata.get("description", "")).lower()

    # Khởi tạo điểm thành phần (Thang 10 điểm)
    # P1: Ngữ âm & Bản sắc (3.0 đ)
    # P2: Tách nhạc & Sạch tạp âm (2.5 đ)
    # P3: Âm lượng & Độ tự nhiên (1.5 đ)
    # P4: Thông số kỹ thuật ASR (1.5 đ)
    # P5: Chủ đề & Ngữ cảnh (1.5 đ)
    
    p1 = 3.0
    p2 = 2.5
    p3 = 1.5
    p4 = 1.5
    p5 = 1.5

    # ─────────────────────────────────────────────────────────────
    # TRỤ CỘT 1: BẢO TỒN ĐẶC TRƯNG NGỮ ÂM & BẢN ĐỊA (MAX 3.0)
    # ─────────────────────────────────────────────────────────────
    # 1.1 Kiểm tra TTS / Voice Clone / AI Bot
    # Tính F0 pitch variance bằng autocorrelation trên các frame 30ms
    frame_len = int(sr * 0.03)
    hop = int(sr * 0.01)
    f0_list = []
    
    # Lấy mẫu 300 frame
    for i in range(0, min(total_samples - frame_len, hop * 300), hop):
        seg = data[i:i+frame_len]
        energy = np.sum(seg**2)
        if energy > 0.01:
            corr = np.correlate(seg, seg, mode="full")[frame_len-1:]
            peak_range = corr[int(sr/400):int(sr/60)] # F0 từ 60Hz - 400Hz
            if len(peak_range) > 0 and np.max(peak_range) > 0.3 * corr[0]:
                pitch = sr / (int(sr/400) + np.argmax(peak_range))
                f0_list.append(pitch)

    f0_std = float(np.std(f0_list)) if len(f0_list) > 10 else 0.0
    details["pitch_f0_std"] = round(f0_std, 2)

    is_tts = False
    if any(k in text_lower for k in TTS_KEYWORDS):
        is_tts = True
        reasons.append("TTS/Giọng máy AI (qua từ khóa metadata)")
    elif len(f0_list) > 25 and f0_std < 8.5: # F0 quá đều, phi tự nhiên
        is_tts = True
        reasons.append("TTS/Giọng máy AI (Pitch F0 quá phẳng, độ biến thiên < 8.5Hz)")

    if is_tts:
        return 0.0, "DELETE", {"p1": 0, "p2": 0, "p3": 0, "p4": 0, "p5": 0}, details, reasons

    # 1.2 Kiểm tra Over-smoothing / Bẹt giọng / Khử ồn quá tay
    # Kiểm tra năng lượng dải tần cao (> 6000Hz)
    fft_vals = np.abs(np.fft.rfft(data[:min(total_samples, sr * 5)]))
    freqs = np.fft.rfftfreq(min(total_samples, sr * 5), 1/sr)
    high_freq_energy = np.sum(fft_vals[freqs > 6000]) / (np.sum(fft_vals) + 1e-6)
    details["high_freq_ratio"] = round(float(high_freq_energy), 4)

    is_over_denoised = False
    if high_freq_energy < 0.008: # Mất sạch phụ âm xát, gió, bẹt giọng nặng
        p1 -= 1.5
        is_over_denoised = True
        reasons.append("Over-denoised nặng: Mất phụ âm cao/âm gió (high_freq_ratio < 0.008)")

    # 1.3 Thưởng điểm giọng phương ngữ / bản sắc quý
    has_central_dialect = any(w in text_lower for w in CENTRAL_DIALECT_LEXICON)
    if has_central_dialect:
        p1 = min(p1 + 0.5, 3.0) # Điểm thưởng bản sắc (tối đa 3.0)
        details["has_central_dialect"] = True

    # ─────────────────────────────────────────────────────────────
    # TRỤ CỘT 2: TÁCH NHẠC NỀN & SẠCH TẠP ÂM (MAX 2.5)
    # ─────────────────────────────────────────────────────────────
    # Kiểm tra năng lượng nền (noise floor)
    sorted_powers = np.sort(data**2)
    noise_floor_power = np.mean(sorted_powers[:int(total_samples * 0.15)]) + 1e-10
    peak_power = np.max(sorted_powers) + 1e-10
    snr_est = 10 * np.log10(peak_power / noise_floor_power)
    details["snr_est_db"] = round(float(snr_est), 1)

    has_heavy_music_or_noise = False
    if snr_est < 12.0:
        p2 -= 1.5
        has_heavy_music_or_noise = True
        reasons.append(f"Tạp âm nền/nhạc còn sót lớn (SNR = {snr_est:.1f}dB < 12dB)")
    elif snr_est < 18.0:
        p2 -= 0.5

    # ─────────────────────────────────────────────────────────────
    # TRỤ CỘT 3: ÂM LƯỢNG & ĐỘ TỰ NHIÊN / CẮT CỤT TỪ (MAX 1.5)
    # ─────────────────────────────────────────────────────────────
    # Kiểm tra clipping ở đầu và cuối file (Word cutoff)
    start_boundary_energy = np.mean(np.abs(data[:int(sr * 0.03)]))
    end_boundary_energy = np.mean(np.abs(data[-int(sr * 0.03):]))
    details["start_boundary_energy"] = round(float(start_boundary_energy), 4)
    details["end_boundary_energy"] = round(float(end_boundary_energy), 4)

    is_clipped = False
    if start_boundary_energy > 0.08 or end_boundary_energy > 0.08:
        p3 -= 1.0
        is_clipped = True
        reasons.append("Cắt cụt từ (Boundary clipping: năng lượng mép cắt > 0.08)")

    # ─────────────────────────────────────────────────────────────
    # TRỤ CỘT 4: THÔNG SỐ KỸ THUẬT ASR (MAX 1.5)
    # ─────────────────────────────────────────────────────────────
    # 4.1 Thời lượng: Giữ nguyên thời lượng cắt hiện tại [2.0s, 600.0s]
    is_bad_duration = False
    if duration < 2.0 or duration > 600.0:
        p4 -= 1.0
        is_bad_duration = True
        reasons.append(f"Thời lượng ngoài ngưỡng cho phép ({duration:.1f}s)")

    # 4.2 Tỷ lệ khoảng lặng (Silence Ratio)
    # Frame energy < -35dBFS tính là silence
    frame_30ms = int(sr * 0.03)
    silence_frames = 0
    total_frames = total_samples // frame_30ms
    for i in range(0, total_samples - frame_30ms, frame_30ms):
        rms = np.sqrt(np.mean(data[i:i+frame_30ms]**2) + 1e-12)
        if 20 * np.log10(rms) < -35.0:
            silence_frames += 1

    silence_ratio = (silence_frames / max(total_frames, 1))
    details["silence_ratio"] = round(float(silence_ratio), 3)

    if silence_ratio > 0.25:
        p4 -= 0.5
        reasons.append(f"Tỷ lệ khoảng lặng cao ({silence_ratio*100:.1f}% > 25%)")

    # ─────────────────────────────────────────────────────────────
    # TRỤ CỘT 5: CHỦ ĐỀ & NGỮ CẢNH HỘI THOẠI (MAX 1.5)
    # ─────────────────────────────────────────────────────────────
    is_junk_ad = any(k in text_lower for k in ADS_JUNK_LEXICON)
    if is_junk_ad:
        p5 = 0.0
        reasons.append("Chủ đề rác: Quảng cáo/Bán hàng/Livestream/TikTok Shop")

    # ─────────────────────────────────────────────────────────────
    # TỔNG KẾT ĐIỂM SỐ & QUYẾT ĐỊNH (KEEP / RECRAWL / DELETE)
    # ─────────────────────────────────────────────────────────────
    total_score = max(0.0, round(p1 + p2 + p3 + p4 + p5, 1))
    pillar_scores = {
        "P1_Ngữ_âm_bản_địa": round(p1, 1),
        "P2_Tách_nhạc_tạp_âm": round(p2, 1),
        "P3_Tự_nhiên_không_cắt_cụt": round(p3, 1),
        "P4_Thông_số_ASR": round(p4, 1),
        "P5_Chủ_đề_ngữ_cảnh": round(p5, 1),
    }

    # RA QUYẾT ĐỊNH:
    # 1. DELETE: Rác bán hàng, TTS bot, nhạc nền phá hủy âm thanh hoàn toàn, file hỏng
    if is_tts or is_junk_ad or total_score < 4.0:
        decision = "DELETE"
        if not reasons: reasons.append("Điểm chất lượng dưới ngưỡng sàn (< 4.0đ)")
    # 2. RECRAWL: Có giá trị phương ngữ hoặc bài giảng quý NHƯNG bị over-denoise hoặc cắt cụt từ
    elif is_over_denoised or is_clipped or has_heavy_music_or_noise:
        decision = "RECRAWL"
        if is_over_denoised: reasons.append("Cần cào lại bản âm mộc gốc (raw) để tránh bẹt giọng/mất ngữ âm")
        if is_clipped: reasons.append("Cần cào lại và cắt chuẩn mép VAD để không mất âm đầu/đuôi")
    # 3. KEEP (PASS): Đạt chuẩn ASR
    elif total_score >= 7.5:
        decision = "KEEP"
        reasons.append("Đạt chuẩn ASR chất lượng cao, giữ trọn vẹn ngữ âm")
    else:
        decision = "KEEP" if total_score >= 6.5 else "RECRAWL"

    return total_score, decision, pillar_scores, details, reasons

if __name__ == "__main__":
    print("Module qc_asr_specialist_evaluator đã sẵn sàng!")
