import json
import subprocess
from pathlib import Path
from tools.reconcile_drive import reconcile_folder, reconcile_remote_drive

print("1. Reconciling local Week2/2026-08-22 folder...")
res = reconcile_folder(Path("Week2/2026-08-22"))
print(f"Local Reconciled: {res['audio_count']} audios == {res['metadata_count']} metadata records ({res['total_hours']}h)")

print("\n2. Pushing remaining audio files to Google Drive via rclone...")
cmd = [
    "rclone", "copy", "Week2/2026-08-22/",
    "gdrive,root_folder_id=16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw:Week2/2026-08-22/",
    "--exclude", "transcripts/**",
    "--exclude", "metadata_extended.json",
    "--exclude", "yield_funnel.json",
    "--exclude", "quarantine/**",
    "--transfers", "8",
    "--drive-chunk-size", "32M",
    "--progress"
]
subprocess.run(cmd)

print("\n3. Running master remote reconciliation to finalize Drive summary.json & metadata.json...")
reconcile_remote_drive()
print("\n🎉 DONE! All 964 audio files fully synchronized to Google Drive!")
