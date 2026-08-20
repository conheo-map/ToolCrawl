"""
tools/check_urls.py — Cong cu kiem tra va xuat bao cao trang thai danh sach link (URL Status Inspector & JSON Exporter).

Tinh nang:
  1. Thong ke so luong link: Da tai (Downloaded), Dang cho (Pending), Loi (Failed).
  2. Xuat danh sach duoi link / Video ID dang JSON de dua qua AI phan tich.
  3. Xuat file pending_urls.txt chua rieng cac link chua tai de cao tiep.

Cach dung:
  python tools/check_urls.py
  python tools/check_urls.py --file urls.txt --json
  python tools/check_urls.py --export-pending pending.txt
  python tools/check_urls.py --export-done-ids done_ids.json
"""

import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime

# Dam bao in tieng Viet va emoji khong bi loi tren Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Regex pattern cho TikTok & Facebook ID
TIKTOK_PATTERN = re.compile(r'/video/(\d{8,19})')
FB_PATTERN = re.compile(r'(?:reel|videos|watch\?v=)/(\d{8,25})')


def extract_id(url: str) -> tuple[str, str | None]:
    """Tra ve (platform, video_id)."""
    m_tt = TIKTOK_PATTERN.search(url)
    if m_tt:
        return "tiktok", m_tt.group(1)
    
    m_fb = FB_PATTERN.search(url)
    if m_fb:
        return "facebook", m_fb.group(1)

    nums = re.findall(r'\d{12,19}', url)
    if nums:
        return "tiktok" if "tiktok" in url else "facebook", nums[0]

    return "unknown", None


def load_seen_ids() -> set[str]:
    """Load toan bo ID da tai tu .checkpoints/seen_ids.json."""
    seen_path = Path(".checkpoints/seen_ids.json")
    if seen_path.exists():
        try:
            data = json.loads(seen_path.read_text(encoding="utf-8"))
            return set(data.get("seen_ids", []))
        except Exception:
            pass
    return set()


def load_metadata_records() -> dict[str, dict]:
    """Load metadata hien co (tra ve dict: item_id -> record)."""
    records = {}
    for meta_file in Path(".").glob("Week*/*/metadata.json"):
        try:
            items = json.loads(meta_file.read_text(encoding="utf-8"))
            for r in items:
                iid = r.get("item_id")
                if iid:
                    records[iid] = r
        except Exception:
            pass
    return records


def load_failed_urls() -> dict[str, str]:
    """Load danh sach link bi loi tu thu muc errors/."""
    failed = {}
    for err_file in Path("errors").glob("failed_*.jsonl"):
        try:
            lines = err_file.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if line.strip():
                    d = json.loads(line)
                    url = d.get("url")
                    if url:
                        failed[url] = d.get("error", "Unknown error")
        except Exception:
            pass
    return failed


def audit_urls(url_file: Path) -> dict:
    """Kiem tra va phan loai toan bo URLs trong file."""
    if not url_file.exists():
        return {"error": f"File khong ton tai: {url_file}"}

    lines = url_file.read_text(encoding="utf-8-sig").splitlines()
    raw_urls = [
        line.strip().lstrip('\ufeff') for line in lines
        if line.strip() and not line.strip().lstrip('\ufeff').startswith("#")
    ]

    seen_ids = load_seen_ids()
    meta_map = load_metadata_records()
    failed_map = load_failed_urls()

    downloaded = []
    pending = []
    failed = []

    for url in raw_urls:
        platform, vid_id = extract_id(url)
        item_id = f"tt_{vid_id}" if platform == "tiktok" else f"fb_{vid_id}"

        if vid_id and (item_id in seen_ids or vid_id in seen_ids or any(vid_id in s for s in seen_ids)):
            meta = meta_map.get(item_id, {})
            downloaded.append({
                "video_id": vid_id,
                "item_id": item_id,
                "platform": platform,
                "url": url,
                "duration_seconds": meta.get("duration_seconds"),
                "language_region": meta.get("language_region", "auto"),
                "title": meta.get("title", ""),
                "status": "DOWNLOADED"
            })
        elif url in failed_map:
            failed.append({
                "video_id": vid_id,
                "url": url,
                "reason": failed_map[url],
                "status": "FAILED"
            })
        else:
            pending.append({
                "video_id": vid_id,
                "url": url,
                "status": "PENDING"
            })

    return {
        "summary": {
            "total_urls_in_file": len(raw_urls),
            "downloaded_count": len(downloaded),
            "pending_count": len(pending),
            "failed_count": len(failed),
            "completion_rate": f"{(len(downloaded) / len(raw_urls) * 100):.1f}%" if raw_urls else "0%",
            "audited_at": datetime.now().isoformat(timespec="seconds")
        },
        "downloaded_ids": [d["video_id"] for d in downloaded if d["video_id"]],
        "downloaded": downloaded,
        "pending": pending,
        "failed": failed
    }


def main():
    parser = argparse.ArgumentParser(description="Cong cu kiem tra & xuat trang thai danh sach link (JSON Exporter)")
    parser.add_argument("--file", "-f", default="urls.txt", help="Duong dan den file URLs can kiem tra (mac dinh: urls.txt)")
    parser.add_argument("--json", "-j", action="store_true", help="In ket qua toan bo dang JSON ra terminal")
    parser.add_argument("--export-json", help="Luu toan bo ket qua phan tich vao file JSON chi dinh")
    parser.add_argument("--export-done-ids", help="Chi xuat mang JSON chua cac Video ID da tai xong (dua qua AI)")
    parser.add_argument("--export-pending", help="Luu cac link chua tai vao file txt moi de chay tiep")
    args = parser.parse_args()

    file_path = Path(args.file)
    result = audit_urls(file_path)

    if "error" in result:
        print(f"Loi: {result['error']}")
        return

    summary = result["summary"]

    # 1. Xuat file neu co yeu cau
    if args.export_json:
        out_p = Path(args.export_json)
        out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Da luu bao cao JSON toan bo vao: {out_p.resolve()}")

    if args.export_done_ids:
        out_ids = Path(args.export_done_ids)
        out_ids.write_text(json.dumps(result["downloaded_ids"], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Da xuat {len(result['downloaded_ids'])} Video ID da tai vao file JSON: {out_ids.resolve()}")

    if args.export_pending:
        out_pend = Path(args.export_pending)
        pending_lines = [p["url"] for p in result["pending"]]
        out_pend.write_text("\n".join(pending_lines) + "\n", encoding="utf-8")
        print(f"Da luu {len(pending_lines)} link chua tai vao: {out_pend.resolve()}")

    # 2. In ra man hinh
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not (args.export_json or args.export_done_ids or args.export_pending):
        print("\n" + "=" * 60)
        print(f"BAO CAO TINH TRANG DANH SACH LINK: {file_path.name}")
        print("=" * 60)
        print(f"* Tong so link trong file:   {summary['total_urls_in_file']}")
        print(f"* Da tai thanh cong:         {summary['downloaded_count']} ({summary['completion_rate']})")
        print(f"* Chua tai (dang cho):       {summary['pending_count']}")
        print(f"* Bi loi / Qua dai:         {summary['failed_count']}")
        print("=" * 60)
        
        if result["downloaded_ids"]:
            print(f"\nMau 5 Video ID da tai xong (dang JSON):")
            print(json.dumps(result["downloaded_ids"][:5], indent=2))
            print(f"\nDe xuat toan bo mang ID dang JSON dua vao AI, chay lenh:")
            print(f"   python tools/check_urls.py --export-done-ids done_ids.json")
            print(f"De xuat danh sach cac link con lai chua cao de chay tiep:")
            print(f"   python tools/check_urls.py --export-pending remaining_urls.txt\n")


if __name__ == "__main__":
    main()
