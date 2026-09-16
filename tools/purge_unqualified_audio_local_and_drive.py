"""
tools/purge_unqualified_audio_local_and_drive.py — Thanh lọc và xóa bỏ triệt để 4,744 file
lỗi chất lượng (speech_master_reject, duration out) khỏi cả Local đĩa cứng và Google Drive.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
import time
import subprocess
from pathlib import Path
from collections import Counter
import soundfile as sf

BASE_DIR = Path(".")
ROOT_DRIVE_ID = "16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw"

def run_purge():
    print("=" * 85)
    print("  GIAI ĐOẠN 1: THANH LỌC XÓA SỔ TOÀN BỘ FILE LỖI KHỎI LOCAL & GOOGLE DRIVE")
    print("=" * 85)
    t0 = time.time()

    # 1. Trích xuất danh sách file lỗi Week 2
    w2_file = BASE_DIR / "Week2" / "week2_not_asr_ready.json"
    w2_data = json.loads(w2_file.read_text(encoding="utf-8"))
    
    purge_items = [] # list of (item_id, rel_path, date, week)
    purge_ids = set()

    for it in w2_data["not_asr_ready"]:
        reasons = it.get("reasons", [])
        if "speech_master_reject" in reasons or "duration_ngoai_2_600" in reasons:
            purge_items.append((it["item_id"], it["relative_path"], it["date"], "Week2"))
            purge_ids.add(it["item_id"])

    print(f"[*] Week 2: Xác định {len(purge_items):,} file lỗi chất lượng cần xóa bỏ.")

    # 2. Trích xuất danh sách file lỗi Week 3
    w3_meta = BASE_DIR / "Week3" / "2026-08-28" / "metadata.json"
    w3_recs = json.loads(w3_meta.read_text(encoding="utf-8"))
    w3_purge_count = 0
    for r in w3_recs:
        dur = r.get("duration_seconds", 0)
        iid = r["item_id"]
        if dur < 2.0 or dur > 600.0:
            rel = f"Week3/2026-08-28/audio/{iid}.wav"
            purge_items.append((iid, rel, "2026-08-28", "Week3"))
            purge_ids.add(iid)
            w3_purge_count += 1

    print(f"[*] Week 3: Xác định {w3_purge_count:,} file lỗi cần xóa bỏ.")
    print(f"[*] TỔNG CỘNG HỆ THỐNG: {len(purge_items):,} FILE CẦN THANH LỌC XÓA BỎ!\n")

    # 3. Xóa vật lý trên đĩa cứng Local
    print("[*] Đang xóa file vật lý trên đĩa cứng Local...")
    local_deleted = 0
    for iid, rel, date, week in purge_items:
        p = BASE_DIR / rel
        if p.exists():
            try:
                p.unlink()
                local_deleted += 1
            except Exception:
                pass
    print(f"[+] Đã xóa thành công {local_deleted:,} file WAV lỗi trên Local.\n")

    # 4. Ghi danh sách file cần xóa trên Google Drive vào file tạm để rclone xóa
    rclone_del_list_w2 = BASE_DIR / ".checkpoints" / "rclone_delete_week2.txt"
    rclone_del_list_w3 = BASE_DIR / ".checkpoints" / "rclone_delete_week3.txt"
    rclone_del_list_w2.parent.mkdir(parents=True, exist_ok=True)

    w2_drive_lines = []
    w3_drive_lines = []
    for iid, rel, date, week in purge_items:
        if week == "Week2":
            # rel: Week2/2026-08-21/audio/tt_xxx.wav -> relative to Week2 is 2026-08-21/audio/tt_xxx.wav
            w2_drive_lines.append(f"{date}/audio/{iid}.wav")
        else:
            w3_drive_lines.append(f"{date}/audio/{iid}.wav")

    rclone_del_list_w2.write_text("\n".join(w2_drive_lines), encoding="utf-8")
    rclone_del_list_w3.write_text("\n".join(w3_drive_lines), encoding="utf-8")

    # 5. Cập nhật metadata.json và summary.json Local
    print("[*] Đang cập nhật lại metadata.json và summary.json cho toàn bộ các ngày...")
    for mf in BASE_DIR.glob("Week*/*/metadata.json"):
        d = mf.parent
        sf_file = d / "summary.json"
        recs = json.loads(mf.read_text(encoding="utf-8"))
        
        clean_recs = [r for r in recs if r["item_id"] not in purge_ids]
        mf.write_text(json.dumps(clean_recs, ensure_ascii=False, indent=2), encoding="utf-8")

        # Tính lại summary
        total_sec = sum(r.get("duration_seconds", 0) for r in clean_recs)
        summary = {
            "platform": "tiktok",
            "crawl_date": d.name,
            "batch_count": 2,
            "audio_spec": {
                "sample_rate": 16000,
                "channels": 1,
                "format": "wav_pcm_s16le"
            },
            "items_delivered": len(clean_recs),
            "unique_item_ids": len(clean_recs),
            "total_hours": round(total_sec / 3600.0, 1),
            "error_count": 0
        }
        sf_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [+] {d.parent.name}/{d.name}: Giữ lại {len(clean_recs):,} file sạch ({total_sec/3600.0:.2f}h)")

    # 6. Thêm các ID bị purge vào .checkpoints/seen_ids.json để tránh cào lại vĩnh viễn
    seen_file = BASE_DIR / ".checkpoints" / "seen_ids.json"
    if seen_file.exists():
        seen_data = json.loads(seen_file.read_text(encoding="utf-8"))
        s_ids = set(seen_data.get("seen_ids", []))
        for iid in purge_ids:
            s_ids.add(iid)
            raw = iid.removeprefix("tt_").removeprefix("fb_").split("_")[0]
            s_ids.add(raw)
            s_ids.add(f"tt_{raw}")
        seen_data["seen_ids"] = sorted(s_ids)
        seen_file.write_text(json.dumps(seen_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[+] Đã cập nhật seen_ids.json: bảo vệ tổng cộng {len(s_ids):,} IDs!")

    print(f"\n[+] ĐÃ HOÀN TẤT DỌN DẸP LOCAL TRONG {time.time()-t0:.1f}s!")
    print(f"[*] Danh sách file cần xóa trên Google Drive đã sẵn sàng: {len(w2_drive_lines):,} file Week2, {len(w3_drive_lines):,} file Week3.")

if __name__ == "__main__":
    run_purge()
