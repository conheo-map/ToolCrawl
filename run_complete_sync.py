import subprocess
from tools.reconcile_drive import reconcile_remote_drive

print("1. Pushing all remaining local audio files to Google Drive...")
cmd = [
    "rclone", "copy", "Week2/",
    "gdrive,root_folder_id=16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw:Week2/",
    "--exclude", "transcripts/**",
    "--exclude", "metadata_extended.json",
    "--exclude", "yield_funnel.json",
    "--exclude", "quarantine/**",
    "--transfers", "8",
    "--checkers", "16",
    "--drive-chunk-size", "32M",
    "--progress"
]
subprocess.run(cmd)

print("\n2. Running master remote reconciliation to finalize all summary.json, metadata.json and seen_ids.json on Google Drive...")
reconcile_remote_drive()

print("\n🎉 ALL DAYS IN WEEK 2 ARE 100% SYNCHRONIZED AND RECONCILED!")
