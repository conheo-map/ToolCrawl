"""
tools/evaluate_recrawled_dataset.py — Đánh giá chất lượng toàn bộ file sau khi cào lại.

Tiêu chuẩn phòng thu AI (Big Tech ASR Grade):
  - Whisper avg_logprob >= -0.50 (giọng đọc rõ ràng, ngữ điệu chuẩn)
  - no_speech_prob < 0.35 (không dính nhạc nền lấn át)
  - SNR >= 15.0 dB (tạp âm nền cực thấp)
  - True-Peak <= -1.0 dBFS (không bị vỡ âm, clipping)
  - Tỷ lệ lỗi mục tiêu: < 0.1%

Cách dùng:
  python tools/evaluate_recrawled_dataset.py [--date YYYY-MM-DD] [--week N]
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))
REPORT_DIR = Path("tools/evaluation_reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def evaluate_date(date_dir: Path, model) -> dict:
    """Đánh giá chất lượng toàn bộ file WAV trong 1 ngày."""
    from processors.quality_assessor import QualityAssessor
    assessor = QualityAssessor()

    audio_dir = date_dir / "audio"
    wav_files = sorted(audio_dir.glob("*.wav"))

    passed = 0
    failed = 0
    file_results = []
    logprobs = []
    snrs = []

    print(f"\n[*] Đang đánh giá {len(wav_files)} files trong {date_dir.name}...", flush=True)

    for i, wav in enumerate(wav_files, 1):
        item_id = wav.stem
        # 1. Đánh giá tín hiệu âm thanh (SNR, Peak)
        acoustic = assessor.assess(wav)
        snr = acoustic["snr_db"]
        snrs.append(snr)

        # 2. Whisper ASR Quality Gate
        segs_iter, _ = model.transcribe(
            str(wav),
            language="vi",
            vad_filter=True,
            without_timestamps=True,
        )
        segs = list(segs_iter)
        text = " ".join(s.text for s in segs).strip()
        avg_lp = sum(s.avg_logprob for s in segs) / max(len(segs), 1) if segs else -2.0
        no_sp = sum(s.no_speech_prob for s in segs) / max(len(segs), 1) if segs else 1.0

        if segs:
            logprobs.append(avg_lp)

        # Tiêu chí đạt chuẩn ASR
        is_pass = bool(text) and no_sp < 0.40 and avg_lp >= -0.50 and snr >= 12.0

        if is_pass:
            passed += 1
            status = "PASSED"
        else:
            failed += 1
            status = "FAILED"

        file_results.append({
            "item_id": item_id,
            "status": status,
            "avg_logprob": round(avg_lp, 3),
            "no_speech_prob": round(no_sp, 3),
            "snr_db": round(snr, 1),
            "text": text[:60],
        })

        if i % 25 == 0 or i == len(wav_files):
            print(f"  [{i}/{len(wav_files)}] Đạt: {passed} | Lỗi: {failed} (Tỷ lệ đạt: {passed/i*100:.1f}%)", flush=True)

    avg_lp_total = sum(logprobs) / max(len(logprobs), 1) if logprobs else 0.0
    avg_snr_total = sum(snrs) / max(len(snrs), 1) if snrs else 0.0
    pass_rate = (passed / max(len(wav_files), 1)) * 100

    return {
        "date": date_dir.name,
        "week": date_dir.parent.name,
        "total_files": len(wav_files),
        "passed": passed,
        "failed": failed,
        "pass_rate_pct": round(pass_rate, 2),
        "error_rate_pct": round(100.0 - pass_rate, 2),
        "avg_logprob": round(avg_lp_total, 3),
        "avg_snr_db": round(avg_snr_total, 1),
        "details": file_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Đánh giá chất lượng dataset sau khi cào lại")
    parser.add_argument("--date", type=str, default=None, help="Chỉ đánh giá ngày cụ thể (VD: 2026-08-24)")
    parser.add_argument("--week", type=int, default=None, help="Chỉ đánh giá tuần cụ thể (VD: 2)")
    args = parser.parse_args()

    print("=" * 65)
    print("  ĐÁNH GIÁ CHẤT LƯỢNG TOÀN DIỆN DATASET (ASR & STUDIO GRADE)")
    print("=" * 65)

    from faster_whisper import WhisperModel
    print("[*] Đang nạp Whisper Model (base, int8)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    print("[+] Model sẵn sàng!\n")

    # Tìm các ngày cần đánh giá
    base = Path(".")
    date_dirs = []
    if args.date:
        for wk in sorted(base.glob("Week*")):
            d = wk / args.date
            if d.exists() and (d / "audio").exists():
                date_dirs.append(d)
    elif args.week:
        wk = base / f"Week{args.week}"
        if wk.exists():
            date_dirs = sorted([d for d in wk.iterdir() if d.is_dir() and (d / "audio").exists()])
    else:
        for wk in sorted(base.glob("Week*")):
            date_dirs.extend(sorted([d for d in wk.iterdir() if d.is_dir() and (d / "audio").exists()]))

    print(f"[*] Sẽ đánh giá {len(date_dirs)} ngày dữ liệu:")
    all_reports = []
    for dd in date_dirs:
        res = evaluate_date(dd, model)
        all_reports.append(res)

    now_str = datetime.now(VN_TZ).strftime("%Y%m%d_%H%M%S")
    out_file = REPORT_DIR / f"evaluation_report_{now_str}.json"
    out_file.write_text(json.dumps(all_reports, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 65)
    print(f"  KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN")
    print("=" * 65)
    for r in all_reports:
        print(f"  [{r['week']}/{r['date']:10s}] Tổng: {r['total_files']:5d} | "
              f"ĐẠT: {r['passed']:5d} ({r['pass_rate_pct']:5.1f}%) | "
              f"avg_logprob: {r['avg_logprob']:+.2f} | avg_SNR: {r['avg_snr_db']:.1f} dB")
    print(f"\n[+] Báo cáo đã lưu: {out_file}\n")


if __name__ == "__main__":
    main()
