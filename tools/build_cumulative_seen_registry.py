"""
tools/build_cumulative_seen_registry.py — Xây dựng sổ bộ định danh toàn cục (seen_ids.json)
Lưu lại vĩnh viễn 100% các ID từng xuất hiện: Thành công, Thất bại, Rác đã xóa, Nhạc bị thanh trừng.
Đảm bảo các crawler tương lai KHÔNG BAO GIỜ cào nhầm hay cào lại!
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

BASE_DIR = Path(".")
SEEN_FILE = Path(".checkpoints/seen_ids.json")
SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)

cumulative_ids = set()

# 1. Đọc seen_ids.json hiện có
if SEEN_FILE.exists():
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        cumulative_ids.update(data.get("seen_ids", []))
    except Exception:
        pass

# 2. Đọc từ tất cả metadata.json (audio hợp lệ)
for mf in BASE_DIR.glob("Week*/*/metadata.json"):
    try:
        records = json.loads(mf.read_text(encoding="utf-8"))
        for r in records:
            iid = r.get("item_id")
            if iid:
                cumulative_ids.add(iid)
                if "_" in iid:
                    cumulative_ids.add("_".join(iid.split("_")[:2]))
                raw = iid.removeprefix("tt_").removeprefix("fb_").split("_")[0]
                cumulative_ids.add(raw)
                cumulative_ids.add(f"tt_{raw}")
    except Exception:
        pass

# 3. Đọc từ tất cả danh sách purge (rác không lời, nhạc, quảng cáo đã xóa)
for pf in BASE_DIR.glob("tools/recrawl_results/*purge*.json"):
    try:
        items = json.loads(pf.read_text(encoding="utf-8"))
        for it in items:
            iid = it.get("item_id")
            if iid:
                cumulative_ids.add(iid)
                if "_" in iid:
                    cumulative_ids.add("_".join(iid.split("_")[:2]))
                raw = iid.removeprefix("tt_").removeprefix("fb_").split("_")[0]
                cumulative_ids.add(raw)
                cumulative_ids.add(f"tt_{raw}")
    except Exception:
        pass

# 4. Đọc từ tất cả file log lỗi (failed_*.jsonl)
for ef in BASE_DIR.glob("errors/failed_*.jsonl"):
    try:
        with open(ef, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                iid = rec.get("item_id")
                if iid:
                    cumulative_ids.add(iid)
                    raw = iid.removeprefix("tt_").removeprefix("fb_").split("_")[0]
                    cumulative_ids.add(raw)
                    cumulative_ids.add(f"tt_{raw}")
    except Exception:
        pass

# 5. Ghi sổ bộ toàn cục
SEEN_FILE.write_text(json.dumps({"seen_ids": sorted(cumulative_ids)}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[+] ĐÃ XÂY DỰNG SỔ BỘ TOÀN CỤC: {len(cumulative_ids):,} ID ĐÃ ĐƯỢC BẢO VỆ VĨNH VIỄN KHỎI CÀO LẠI!")
