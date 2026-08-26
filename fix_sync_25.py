import json
import subprocess
from pathlib import Path
from tools.reconcile_drive import reconcile_folder, reconcile_remote_drive

print("=== KIỂM TRA DỮ LIỆU NGÀY 2026-08-25 ===")
local_dir = Path("Week2/2026-08-25")
if (local_dir / "audio").exists():
    res = reconcile_folder(local_dir)
    print(f"Local 2026-08-25: {res['audio_count']} audios | {res['metadata_count']} records | {res['total_hours']}h")

print("\n=== ĐẨY FILE AUDIO LÊN GOOGLE DRIVE (TỰ ĐỘNG RETRY) ===")
cmd = [
    "rclone", "copy", "Week2/2026-08-25/",
    "gdrive,root_folder_id=16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw:Week2/2026-08-25/",
    "--exclude", "transcripts/**",
    "--exclude", "metadata_extended.json",
    "--exclude", "yield_funnel.json",
    "--exclude", "quarantine/**",
    "--transfers", "8",
    "--retries", "5",
    "--low-level-retries", "10",
    "--drive-chunk-size", "32M",
    "--progress"
]
subprocess.run(cmd)

print("\n=== ĐỐI SOÁT TOÀN DIỆN GOOGLE DRIVE ===")
reconcile_remote_drive()
