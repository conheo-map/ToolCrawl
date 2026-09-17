import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import os
import json
from pathlib import Path

root = Path(r"c:\HocC\SaydiTool")

# Kiem tra ca tren Drive truc tiep hoac local metadata
# 1. Quet cac file metadata.json tren toan bo he thong
meta_files = list(root.glob("**/metadata*.json"))

weeks_data = {
    "Week1": {"files": 0, "duration": 0.0, "dates": set()},
    "Week2": {"files": 0, "duration": 0.0, "dates": set()},
    "Week3": {"files": 0, "duration": 0.0, "dates": set()},
    "Week4": {"files": 0, "duration": 0.0, "dates": set()},
    "Week5": {"files": 0, "duration": 0.0, "dates": set()},
}

# Doc tu local_research va cac thu muc Week
for mf in meta_files:
    # Bo qua checkpoint va file tam
    if ".checkpoints" in str(mf) or "venv" in str(mf) or "errors" in str(mf):
        continue
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            dur = item.get("duration_seconds", item.get("duration", 0.0))
            if dur <= 0:
                continue
            
            # Xac dinh tuan
            cdate = item.get("crawl_date", "")
            path_str = str(mf) + " " + item.get("audio_file", "")
            
            w_key = None
            for w in ["Week1", "Week2", "Week3", "Week4", "Week5"]:
                if w in path_str:
                    w_key = w
                    break
            
            if not w_key and "2026-09-17" in path_str:
                w_key = "Week5"
            elif not w_key and cdate:
                if cdate < "2026-08-24":
                    w_key = "Week1"
                elif cdate <= "2026-08-30":
                    w_key = "Week2"
                elif cdate <= "2026-09-06":
                    w_key = "Week3"
                elif cdate <= "2026-09-13":
                    w_key = "Week4"
                else:
                    w_key = "Week5"

            if w_key:
                # Tranh double count bang item_id
                pass
    except Exception:
        pass

# Doc tu summary.json cua tung folder chuan da sync len Drive
summary_map = {
    "Week1": {"dates": ["2026-08-20", "2026-08-21", "2026-08-22", "2026-08-23"]},
    "Week2": {"dates": ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29", "2026-08-30"]},
    "Week3": {"dates": ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]},
    "Week4": {"dates": ["2026-09-07", "2026-09-10", "2026-09-11", "2026-09-13"]},
    "Week5": {"dates": ["2026-09-14", "2026-09-17"]},
}

results = {}
grand_files = 0
grand_hours = 0.0

for w_name in summary_map:
    results[w_name] = {"files": 0, "hours": 0.0, "dates": []}
    
    # Kiem tra cac file summary / metadata trong local_research hoac folder Week
    for d in summary_map[w_name]["dates"]:
        # Tim folder
        candidates = [
            root / w_name / d,
            root / "local_research" / d,
            root / f"dataset_{d}",
        ]
        found = False
        for c in candidates:
            if (c / "summary.json").exists():
                try:
                    s = json.loads((c / "summary.json").read_text(encoding="utf-8"))
                    f_cnt = s.get("items_delivered", s.get("clean_files_delivered", 0))
                    h_cnt = float(s.get("total_hours", 0.0))
                    if h_cnt == 0.0 and (c / "metadata.json").exists():
                        m = json.loads((c / "metadata.json").read_text(encoding="utf-8"))
                        f_cnt = len(m)
                        h_cnt = sum(it.get("duration_seconds", 0.0) for it in m) / 3600.0
                    results[w_name]["files"] += f_cnt
                    results[w_name]["hours"] += h_cnt
                    results[w_name]["dates"].append(d)
                    found = True
                    break
                except Exception:
                    pass
            elif (c / "metadata.json").exists():
                try:
                    m = json.loads((c / "metadata.json").read_text(encoding="utf-8"))
                    f_cnt = len(m)
                    h_cnt = sum(it.get("duration_seconds", 0.0) for it in m) / 3600.0
                    results[w_name]["files"] += f_cnt
                    results[w_name]["hours"] += h_cnt
                    results[w_name]["dates"].append(d)
                    found = True
                    break
                except Exception:
                    pass
        if not found:
            # Thu tim file audit json
            audit_f = root / "local_research" / f"audit_{w_name.lower()}_full.json"
            if audit_f.exists():
                pass

print("=" * 80)
print("📊 BÁO CÁO TỔNG THỜI LƯỢNG AUDIO SẠCH TRÊN GOOGLE DRIVE (WEEK 1 -> WEEK 5)")
print("=" * 80)

for w_name, info in results.items():
    grand_files += info["files"]
    grand_hours += info["hours"]
    print(f"📁 {w_name:6s} : {info['files']:6,d} files audio sạch | {len(info['dates']):2d} ngày | {info['hours']:6.2f} giờ")

print("-" * 80)
print(f"🌟 TỔNG CỘNG TOÀN BỘ (5 TUẦN) : {grand_files:,} FILES AUDIO SẠCH | {grand_hours:.2f} GIỜ")
print("=" * 80)
