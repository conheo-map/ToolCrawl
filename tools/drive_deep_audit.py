"""
tools/drive_deep_audit.py — Kiem tra va doi soat toan dien Google Drive vs Bao cao.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
import subprocess
from pathlib import Path

ROOT_ID = "16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw"

print("================================================================")
print("SAYDITOOL COMPREHENSIVE DRIVE VS REPORT DEEP AUDIT")
print("================================================================")

# 1. Tim cac tuan tren Drive
res_weeks = subprocess.run(["rclone", "lsf", f"gdrive,root_folder_id={ROOT_ID}:", "--dirs-only"], capture_output=True, text=True, encoding="utf-8")
weeks = []
for line in res_weeks.stdout.splitlines():
    w = line.strip().rstrip("/")
    if w.startswith("Week") and w.removeprefix("Week").isdigit():
        weeks.append(w)
weeks = sorted(weeks)

print(f"Phat hien cac tuan tren Google Drive: {', '.join(weeks)}\n")

audit_results = []
grand_actual_hours = 0.0
grand_report_hours = 0.0
grand_drive_files = 0
grand_report_records = 0

for wk in weeks:
    # Liet ke cac ngay trong tuan
    res_dates = subprocess.run(["rclone", "lsf", f"gdrive,root_folder_id={ROOT_ID}:{wk}/", "--dirs-only"], capture_output=True, text=True, encoding="utf-8")
    dates = sorted([d.strip().rstrip("/") for d in res_dates.stdout.splitlines() if d.strip()])

    for d in dates:
        print(f"--- Dang kiem tra {wk}/{d} ---")
        drive_audio_path = f"gdrive,root_folder_id={ROOT_ID}:{wk}/{d}/audio/"
        
        # Lay danh sach file audio va dung luong tren Drive bang rclone lsjson
        res_json = subprocess.run(["rclone", "lsjson", drive_audio_path], capture_output=True, text=True, encoding="utf-8")
        drive_audio_map = {} # item_id -> {"filename": str, "size": int, "calc_duration": float}
        if res_json.returncode == 0 and res_json.stdout.strip():
            try:
                entries = json.loads(res_json.stdout)
                for entry in entries:
                    name = entry.get("Name", "")
                    if name.endswith(".wav"):
                        item_id = name[:-4]
                        size = entry.get("Size", 0)
                        # PCM 16kHz 16-bit Mono: (size - 44 bytes header) / (16000 * 2)
                        calc_dur = max(0.0, (size - 44) / 32000.0)
                        drive_audio_map[item_id] = {
                            "filename": name,
                            "size": size,
                            "calc_duration": round(calc_dur, 2)
                        }
            except Exception as e:
                print(f"  Loi parse lsjson {wk}/{d}: {e}")

        # Doc summary.json tu Drive
        res_summary = subprocess.run(["rclone", "cat", f"gdrive,root_folder_id={ROOT_ID}:{wk}/{d}/summary.json"], capture_output=True, text=True, encoding="utf-8")
        summary_data = {}
        if res_summary.returncode == 0 and res_summary.stdout.strip():
            try:
                summary_data = json.loads(res_summary.stdout)
            except Exception:
                pass

        # Doc metadata.json tu Drive
        res_meta = subprocess.run(["rclone", "cat", f"gdrive,root_folder_id={ROOT_ID}:{wk}/{d}/metadata.json"], capture_output=True, text=True, encoding="utf-8")
        meta_records = []
        if res_meta.returncode == 0 and res_meta.stdout.strip():
            try:
                meta_records = json.loads(res_meta.stdout)
            except Exception:
                pass

        meta_map = {r["item_id"]: r for r in meta_records if isinstance(r, dict) and "item_id" in r}

        # So sanh 4 truong hop:
        exact_matches = []
        diff_duration = []
        drive_only = []
        report_only = []

        all_ids = set(drive_audio_map.keys()) | set(meta_map.keys())

        day_actual_sec = sum(f["calc_duration"] for f in drive_audio_map.values())
        day_report_sec = sum(r.get("duration_seconds", 0) for r in meta_records)

        for i_id in all_ids:
            in_drive = i_id in drive_audio_map
            in_report = i_id in meta_map

            if in_drive and in_report:
                d_dur = drive_audio_map[i_id]["calc_duration"]
                r_dur = meta_map[i_id].get("duration_seconds", 0.0)
                diff = round(d_dur - r_dur, 3)

                if abs(diff) <= 1.0:
                    exact_matches.append((i_id, d_dur, r_dur, diff))
                else:
                    diff_duration.append((i_id, d_dur, r_dur, diff))
            elif in_drive and not in_report:
                drive_only.append((i_id, drive_audio_map[i_id]["calc_duration"]))
            elif not in_drive and in_report:
                report_only.append((i_id, meta_map[i_id].get("duration_seconds", 0.0)))

        day_actual_hours = round(day_actual_sec / 3600.0, 2)
        day_report_hours = round(summary_data.get("total_hours", day_report_sec / 3600.0), 2)
        summary_items = summary_data.get("items_delivered", len(meta_records))

        grand_actual_hours += day_actual_hours
        grand_report_hours += day_report_hours
        grand_drive_files += len(drive_audio_map)
        grand_report_records += len(meta_records)

        audit_results.append({
            "week": wk,
            "date": d,
            "drive_files": len(drive_audio_map),
            "report_records": len(meta_records),
            "summary_items": summary_items,
            "actual_hours": day_actual_hours,
            "report_hours": day_report_hours,
            "exact_count": len(exact_matches),
            "diff_count": len(diff_duration),
            "drive_only_count": len(drive_only),
            "report_only_count": len(report_only),
            "diff_samples": diff_duration[:5],
            "drive_only_samples": drive_only[:5],
            "report_only_samples": report_only[:5]
        })
        print(f"  -> Drive: {len(drive_audio_map)} files ({day_actual_hours}h) | Report: {len(meta_records)} recs ({day_report_hours}h) | Khop: {len(exact_matches)} | Lech: {len(diff_duration)} | Drive only: {len(drive_only)} | Report only: {len(report_only)}")

print("\nSaving audit report to audit_summary.json...")
Path("audit_summary.json").write_text(json.dumps({
    "grand_actual_hours": round(grand_actual_hours, 2),
    "grand_report_hours": round(grand_report_hours, 2),
    "grand_drive_files": grand_drive_files,
    "grand_report_records": grand_report_records,
    "details": audit_results
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Audit complete! Report saved.")
