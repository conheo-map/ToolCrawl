"""
tools/gdrive_fast_downloader.py — High-Speed Resilient Google Drive Downloader with Live Progress.
"""

from __future__ import annotations

import os
import sys
import time
import json
import configparser
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests

ROOT = Path(__file__).resolve().parent.parent


def get_gdrive_credentials() -> tuple[str, str]:
    rclone_conf = Path("/root/.config/rclone/rclone.conf")
    if not rclone_conf.exists():
        rclone_conf = Path.home() / "AppData" / "Roaming" / "rclone" / "rclone.conf"
    if not rclone_conf.exists():
        rclone_conf = Path.home() / ".config" / "rclone" / "rclone.conf"

    if not rclone_conf.exists():
        raise FileNotFoundError(f"Không tìm thấy rclone.conf tại: {rclone_conf}")

    config = configparser.ConfigParser()
    config.read(rclone_conf, encoding="utf-8")
    section = "gdrive" if "gdrive" in config else config.sections()[0]

    token_str = config.get(section, "token")
    token_json = json.loads(token_str)
    access_token = token_json["access_token"]
    root_id = config.get(section, "root_folder_id", fallback="16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw")
    return access_token, root_id


def list_files_in_folder(access_token: str, folder_id: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    items = []
    page_token = None

    while True:
        url = "https://www.googleapis.com/drive/v3/files"
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, size)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token

        for attempt in range(8):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    items.extend(data.get("files", []))
                    page_token = data.get("nextPageToken")
                    time.sleep(0.1)
                    break
                elif resp.status_code in (403, 429, 500, 503):
                    wait_sec = 2 * (attempt + 1)
                    time.sleep(wait_sec)
                else:
                    break
            except Exception:
                time.sleep(2.0)

        if not page_token:
            break

    return items


def download_single_file(access_token: str, file_id: str, dst_path: Path) -> bool:
    if dst_path.exists() and dst_path.stat().st_size > 1000:
        return True

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    tmp_path = dst_path.with_suffix(".tmp")
    for attempt in range(8):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 200:
                    with open(tmp_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                    tmp_path.rename(dst_path)
                    return True
                elif r.status_code in (403, 429, 500, 503):
                    time.sleep(2 * (attempt + 1))
                else:
                    return False
        except Exception:
            time.sleep(2.0)

    if tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
    return False


def sync_week_from_drive(target_week: str, workers: int = 16):
    access_token, root_id = get_gdrive_credentials()
    print(f"[*] Đang quét danh mục trên Google Drive cho {target_week}...", flush=True)

    root_items = list_files_in_folder(access_token, root_id)
    week_folder = next((it for it in root_items if it["name"] == target_week and it["mimeType"] == "application/vnd.google-apps.folder"), None)

    if not week_folder:
        print(f"[-] Không tìm thấy folder {target_week} trên Drive!", flush=True)
        return

    print(f"[+] Đã tìm thấy {target_week}. Đang quét các ngày...", flush=True)
    date_folders = list_files_in_folder(access_token, week_folder["id"])

    all_download_tasks = []
    dst_root = ROOT / f"{target_week}_cu"

    for d_folder in date_folders:
        if d_folder["mimeType"] != "application/vnd.google-apps.folder":
            continue
        day_str = d_folder["name"]
        print(f"  - Đang quét ngày {day_str}...", flush=True)
        day_items = list_files_in_folder(access_token, d_folder["id"])

        for it in day_items:
            if it["mimeType"] == "application/vnd.google-apps.folder" and it["name"] == "audio":
                audio_files = list_files_in_folder(access_token, it["id"])
                print(f"    -> Ngày {day_str}: Tìm thấy {len(audio_files)} files audio", flush=True)
                for af in audio_files:
                    if af["name"].endswith(".wav"):
                        dst_file = dst_root / day_str / "audio" / af["name"]
                        all_download_tasks.append((af["id"], dst_file, af["name"]))
            elif it["name"] in ("metadata.json", "summary.json"):
                dst_file = dst_root / day_str / it["name"]
                all_download_tasks.append((it["id"], dst_file, it["name"]))

    print(f"\n[+] Tổng số file cần tải cho {target_week}: {len(all_download_tasks):,} files", flush=True)
    to_download = [t for t in all_download_tasks if not (t[1].exists() and t[1].stat().st_size > 1000)]
    print(f"[*] Đã có sẵn: {len(all_download_tasks) - len(to_download):,} files -> Cần tải mới: {len(to_download):,} files\n", flush=True)

    if not to_download:
        print(f"🎉 {target_week} ĐÃ ĐẦY ĐỦ 100% TRÊN MÁY!", flush=True)
        return

    t0 = time.time()
    done_count = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_single_file, access_token, t[0], t[1]): t for t in to_download}
        for fut in as_completed(futures):
            t = futures[fut]
            done_count += 1
            ok = fut.result()
            if done_count % 50 == 0 or done_count == len(to_download):
                speed = done_count / max(0.1, time.time() - t0)
                pct = (done_count / len(to_download)) * 100
                print(f"[{done_count}/{len(to_download)}] ({pct:.1f}%) Đang tải {target_week} ({speed:.1f} file/s)...", flush=True)

    print(f"\n🎉 HOÀN TẤT TẢI {target_week} TRONG {(time.time()-t0)/60:.2f} PHÚT!", flush=True)


if __name__ == "__main__":
    w_arg = sys.argv[1] if len(sys.argv) > 1 else "Week2"
    sync_week_from_drive(w_arg, workers=16)
