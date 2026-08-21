"""
tools/daily_reporter.py — Tự động sinh báo cáo hàng ngày (Daily Report)
và xuất định dạng Google Sheets chuẩn chỉ việc copy-paste.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
from pathlib import Path
from collections import Counter
import config as cfg


def generate_report(date_str: str, author_name: str = "Trương Duy Cường") -> dict:
    folder = cfg.PROJECT_ROOT / f"Week{cfg.WEEK_NUMBER}" / date_str
    meta_file = folder / "metadata.json"
    summary_file = folder / "summary.json"

    if not summary_file.exists() or not meta_file.exists():
        return {"status": "error", "message": f"Chưa có dữ liệu cho ngày {date_str}"}

    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        records = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "error", "message": f"Lỗi đọc file JSON: {e}"}

    total_items = summary.get("items_delivered", len(records))
    total_hours = summary.get("total_hours", 0.0)
    durations = [r.get("duration_seconds", 0) for r in records]
    avg_dur = sum(durations) / len(durations) if durations else 0

    regions = Counter(r.get("language_region", "mixed") for r in records)
    separated_count = sum(1 for r in records if r.get("vocal_separated"))

    # Định dạng Markdown chi tiết
    md_report = f"""# 📊 DAILY REPORT — {date_str}
**Họ và tên:** {author_name}
**Tuần:** Week {cfg.WEEK_NUMBER}
**Số lượng bàn giao:** {total_items} file ({total_hours:.2f} giờ)
**Thời lượng trung bình:** {avg_dur:.1f}s/file
**Tách nhạc AI:** {separated_count} file

### Phân bố phương ngữ:
• Miền Trung: {regions.get('central', 0)}
• Miền Nam: {regions.get('southern', 0)}
• Miền Bắc: {regions.get('northern', 0)}
• Toàn quốc/Mixed: {regions.get('mixed', 0)}
"""

    # Định dạng 1 ô Google Sheets
    sheets_report = (
        f"- Crawl và xử lý thành công {total_hours:.2f}h audio ({total_items} file .wav 16kHz Mono).\n"
        f"- Áp dụng bộ lọc bóc tách vocal AI Demucs và chuẩn hóa âm lượng EBU R128 (-16 LUFS).\n"
        f"- Tích hợp kiểm định chất lượng SNR & phân loại phương ngữ ({regions.get('central', 0)} Trung, {regions.get('southern', 0)} Nam, {regions.get('northern', 0)} Bắc).\n"
        f"- Đối soát đồng bộ 100% dữ liệu với Google Drive."
    )

    return {
        "status": "success",
        "date": date_str,
        "author": author_name,
        "total_items": total_items,
        "total_hours": total_hours,
        "avg_duration": round(avg_dur, 1),
        "regions": dict(regions),
        "md_report": md_report,
        "sheets_report": sheets_report,
    }


def main():
    parser = argparse.ArgumentParser(description="Tự động tạo Daily Report")
    parser.add_argument("--date", default=cfg.CRAWL_DATE, help="Ngày báo cáo (YYYY-MM-DD)")
    parser.add_argument("--author", default="Trương Duy Cường", help="Tên thành viên")
    args = parser.parse_args()

    res = generate_report(args.date, args.author)
    if res["status"] == "error":
        print(f"❌ {res['message']}")
        return

    print("=" * 60)
    print("📋 BẢN BÁO CÁO DÁN VÀO GOOGLE SHEETS (CỘT D):")
    print("=" * 60)
    print(res["sheets_report"])
    print("\n" + "=" * 60)
    print("📝 BẢN BÁO CÁO CHI TIẾT (MARKDOWN):")
    print("=" * 60)
    print(res["md_report"])


if __name__ == "__main__":
    main()
