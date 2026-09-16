"""
tools/purge_garbage_system.py — Xóa bỏ hoàn toàn các file rác khỏi cả Local và Google Drive.

Chức năng:
  1. Đọc purge_list.json (danh sách các file rác thực sự: không có tiếng nói, thuần nhạc meme).
  2. Xóa file WAV vật lý trên ổ đĩa cục bộ (WeekX/YYYY-MM-DD/audio/ID.wav).
  3. Xóa file tương ứng trên Google Drive bằng `rclone deletefile`.
  4. Cập nhật metadata.json của ngày: gỡ bỏ hoàn toàn record của file rác.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(".")
RESULT_DIR = Path("tools/recrawl_results")
ROOT_DRIVE_ID = "16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw"


def run_purge(purge_file: Path = RESULT_DIR / "purge_list.json"):
    print("=" * 80)
    print("  HỆ THỐNG THANH TRỪNG & XÓA BỎ FILE RÁC TRÊN CẢ LOCAL VÀ GOOGLE DRIVE")
    print("=" * 80)
    t0 = time.time()

    if not purge_file.exists():
        print(f"[!] Không tìm thấy file {purge_file}. Hãy chạy pipeline sàng lọc trước.")
        return

    items = json.loads(purge_file.read_text(encoding="utf-8"))
    print(f"[*] Tổng số file rác cần xóa bỏ vĩnh viễn: {len(items):,} file\n")

    local_deleted = 0
    drive_deleted = 0
    date_to_deleted_ids = {}
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def purge_one_item(item):
        item_id = item["item_id"]
        week = item.get("week")
        date = item.get("date")
        rel_path = item.get("relative_path") or f"{week}/{date}/audio/{item_id}.wav"
        local_path = BASE_DIR / rel_path

        local_ok = False
        if local_path.exists():
            try:
                local_path.unlink()
                local_ok = True
            except Exception:
                pass

        drive_ok = False
        drive_file_path = f"gdrive,root_folder_id={ROOT_DRIVE_ID}:{rel_path}"
        try:
            res = subprocess.run(["rclone", "deletefile", drive_file_path], capture_output=True, timeout=25)
            if res.returncode == 0:
                drive_ok = True
        except Exception:
            pass

        return item_id, week, date, local_ok, drive_ok

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(purge_one_item, it): it for it in items}
        done = 0
        for f in as_completed(futures):
            done += 1
            item_id, week, date, loc_ok, drv_ok = f.result()
            if loc_ok:
                local_deleted += 1
            if drv_ok:
                drive_deleted += 1

            date_key = (week, date)
            date_to_deleted_ids.setdefault(date_key, set()).add(item_id)
            base_id = item_id.removeprefix("tt_").removeprefix("fb_").split("_")[0]
            date_to_deleted_ids[date_key].add(base_id)

            if done % 50 == 0 or done == len(items):
                print(f"  [{done}/{len(items)}] Đã xóa Local: {local_deleted} | Đã xóa Drive: {drive_deleted}", flush=True)

    # 3. Làm sạch metadata.json của các ngày liên quan
    print("\n[*] Đang làm sạch metadata.json của các thư mục ngày...")
    for (week, date), del_ids in date_to_deleted_ids.items():
        meta_file = BASE_DIR / week / date / "metadata.json"
        if meta_file.exists():
            try:
                records = json.loads(meta_file.read_text(encoding="utf-8"))
                clean_records = [r for r in records if r.get("item_id") not in del_ids and r.get("item_id", "").split("_")[0] not in del_ids]
                removed = len(records) - len(clean_records)
                meta_file.write_text(json.dumps(clean_records, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  [{week}/{date}] Đã loại bỏ {removed} record rác khỏi metadata.json")
            except Exception as e:
                print(f"  [!] Lỗi cập nhật metadata {meta_file}: {e}")

    elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print(f"  HOÀN TẤT THANH TRỪNG ({elapsed:.1f}s)")
    print(f"  Tổng file rác đã xóa trên Local : {local_deleted:,} file")
    print(f"  Tổng file rác đã xóa trên Drive : {drive_deleted:,} file")
    print("=" * 80)


if __name__ == "__main__":
    run_purge()
