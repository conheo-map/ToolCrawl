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
    access_token = token_json.get("access_token", "")
    refresh_token = token_json.get("refresh_token", "")
    client_id = config.get(section, "client_id", fallback="")
    client_secret = config.get(section, "client_secret", fallback="")
    root_id = config.get(section, "root_folder_id", fallback="16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw")

    # Auto refresh token if expired
    if refresh_token:
        try:
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
            res = requests.post(token_url, data=data, timeout=10)
            if res.status_code == 200:
                new_tok = res.json().get("access_token")
                if new_tok:
                    access_token = new_tok
        except Exception:
            pass

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
                    time.sleep(0.05)
                    break
                elif resp.status_code in (403, 429, 500, 503):
                    wait_sec = 2 * (attempt + 1)
                    time.sleep(wait_sec)
                else:
                    break
            except Exception:
                time.sleep(2)

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


def sync_week_from_drive(target_week: str, filter_group: str = "all", workers: int = 16):
    access_token, root_id = get_gdrive_credentials()
    w_num = target_week.replace("Week", "").replace("week", "")
    audit_file = ROOT / "local_research" / f"audit_week{w_num}_full.json"
    
    rec_map = {}
    if audit_file.exists():
        try:
            audit = json.loads(audit_file.read_text(encoding="utf-8"))
            rec_map = {r["item_id"]: str(r.get("group", "")).lower() for r in audit.get("records", [])}
        except Exception:
            pass

    print(f"[*] Đang quét danh mục trên Google Drive cho {target_week} (Nhóm: {filter_group.upper()})...", flush=True)

    root_items = list_files_in_folder(access_token, root_id)
    folders = [it for it in root_items if it["mimeType"] == "application/vnd.google-apps.folder"]
    
    target_clean = target_week.lower().replace(" ", "").replace("_", "")
    week_folder = next((it for it in folders if it["name"].lower().replace(" ", "").replace("_", "") == target_clean), None)

    if not week_folder:
        # Fallback: Search globally for the folder on Drive
        headers = {"Authorization": f"Bearer {access_token}"}
        url = "https://www.googleapis.com/drive/v3/files"
        q = f"mimeType = 'application/vnd.google-apps.folder' and (name contains '{target_week}' or name contains 'Week {w_num}' or name contains 'Week_{w_num}') and trashed = false"
        params = {"q": q, "fields": "files(id, name)", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                found_folders = resp.json().get("files", [])
                if found_folders:
                    week_folder = found_folders[0]
        except Exception:
            pass

    if not week_folder:
        print(f"[-] Không tìm thấy folder khớp với '{target_week}' trên Drive!", flush=True)
        print(f"[*] Các folder đang có trong root: {[it['name'] for it in folders]}", flush=True)
        return

    print(f"[+] Đã tìm thấy '{week_folder['name']}' (ID: {week_folder['id']}). Đang quét các ngày...", flush=True)
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
                for af in audio_files:
                    if af["name"].endswith(".wav"):
                        item_id = af["name"][:-4]
                        raw_grp = rec_map.get(item_id, "")
                        is_3b = "3b" in raw_grp or "heavy" in raw_grp
                        is_3a = "3a" in raw_grp or "moderate" in raw_grp

                        if filter_group == "3b" and not is_3b and rec_map:
                            continue
                        if filter_group == "3a" and not is_3a and rec_map:
                            continue

                        dst_file = dst_root / day_str / "audio" / af["name"]
                        all_download_tasks.append((af["id"], dst_file, af["name"]))
            elif it["name"] in ("metadata.json", "summary.json"):
                dst_file = dst_root / day_str / it["name"]
                all_download_tasks.append((it["id"], dst_file, it["name"]))

    print(f"\n[+] Tổng số file cần tải cho {target_week} (Nhóm {filter_group.upper()}): {len(all_download_tasks):,} files", flush=True)
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("week", type=str, default="Week2", nargs="?", help="Week name e.g. Week2, Week3, Week4, all")
    parser.add_argument("--group", choices=["3a", "3b", "all"], default="all", help="Filter group")
    parser.add_argument("--workers", type=int, default=16, help="Parallel download workers")
    args = parser.parse_args()

    target_weeks = ["Week1", "Week2", "Week3", "Week4"] if args.week == "all" else [args.week]
    for w in target_weeks:
        sync_week_from_drive(w, filter_group=args.group, workers=args.workers)
