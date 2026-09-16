
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import subprocess
import time
from pathlib import Path

BASE_DIR = Path('.')
ROOT_DRIVE_ID = '16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw'
OUT_DIR = BASE_DIR / 'tools' / 'reconciliation_results'
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run_reconciliation():
    print('=' * 85)
    print('  ĐỐI SOÁT 3 CHIỀU TOÀN DIỆN KHO DỮ LIỆU:')
    print('  [1] METADATA.JSON  vs  [2] GOOGLE DRIVE AUDIO  vs  [3] LOCAL AUDIO')
    print('=' * 85)
    t0 = time.time()

    # 1. Thu thập dữ liệu LOCAL & METADATA
    print('\n[*] 1. Đang quét dữ liệu Local & metadata.json...')
    local_meta = {}
    local_files = {}

    for mf in sorted(BASE_DIR.glob('Week*/*/metadata.json')):
        d = mf.parent
        w_name = d.parent.name
        d_name = d.name
        audio_dir = d / 'audio'

        recs = json.loads(mf.read_text(encoding='utf-8'))
        for r in recs:
            iid = r['item_id']
            rel_key = f'{w_name}/{d_name}/audio/{iid}.wav'
            local_meta[rel_key] = {
                'item_id': iid,
                'duration_seconds': r.get('duration_seconds', 0.0),
                'folder': f'{w_name}/{d_name}'
            }

        if audio_dir.exists():
            for wf in audio_dir.glob('*.wav'):
                rel_key = f'{w_name}/{d_name}/audio/{wf.name}'
                st = wf.stat()
                local_files[rel_key] = {
                    'size': st.st_size,
                    'duration_seconds': round(st.st_size / 32000.0, 2)
                }

    print(f'  -> Tổng số bản ghi trong metadata.json: {len(local_meta):,}')
    print(f'  -> Tổng số file WAV thực tế trên Local: {len(local_files):,}')

    # 2. Thu thập dữ liệu GOOGLE DRIVE
    print('\n[*] 2. Đang quét toàn bộ danh mục Google Drive qua rclone...')
    drive_files = {}

    # Tự động phát hiện tất cả các tuần hiện có trên Local
    local_weeks = sorted({mf.parent.parent.name for mf in BASE_DIR.glob("Week*/*/metadata.json")})
    # Tự động truy vấn các thư mục Week trên Drive
    drive_weeks_detected = []
    try:
        lsf_cmd = ['rclone', 'lsf', f'gdrive,root_folder_id={ROOT_DRIVE_ID}:', '--dirs-only']
        lsf_res = subprocess.run(lsf_cmd, capture_output=True, text=True, timeout=30)
        if lsf_res.returncode == 0:
            for line in lsf_res.stdout.splitlines():
                line = line.strip().rstrip('/')
                if line.startswith('Week'):
                    drive_weeks_detected.append(line)
    except Exception as exc:
        print(f'  [!] Không thể lấy danh sách tuần từ Drive ({exc}), dùng danh sách Local: {local_weeks}')

    all_target_weeks = sorted(set(local_weeks + drive_weeks_detected))
    if not all_target_weeks:
        all_target_weeks = ['Week2', 'Week3']
    print(f'  -> Các tuần được quét đối soát: {", ".join(all_target_weeks)}')

    for week in all_target_weeks:
        print(f'  -> Đang lấy danh mục {week} từ Google Drive...')
        cmd = [
            'rclone', 'lsjson',
            f'gdrive,root_folder_id={ROOT_DRIVE_ID}:{week}',
            '--recursive',
            '--fast-list'
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f'  [!] Lỗi khi quét {week}: {res.stderr.strip()[:100]}')
            continue

        try:
            items = json.loads(res.stdout)
        except json.JSONDecodeError as exc:
            print(f'  [!] Lỗi giải mã JSON từ rclone {week}: {exc}')
            continue

        count_w = 0
        for it in items:
            p = it['Path']
            if not it.get('IsDir', False) and p.endswith('.wav'):
                rel_key = f'{week}/{p}'
                sz = it['Size']
                drive_files[rel_key] = {
                    'size': sz,
                    'duration_seconds': round(sz / 32000.0, 2),
                    'mod_time': it.get('ModTime', '')
                }
                count_w += 1
        print(f'  -> Đã tìm thấy {count_w:,} file WAV trong {week} trên Drive.')

    print(f'  -> Tổng số file WAV thực tế trên Google Drive: {len(drive_files):,}')

    # 3. ĐỐI SOÁT CHI TIẾT
    print('\n[*] 3. Đang thực thi phân tích đối soát 3 chiều...')

    drive_orphans = []
    for k, v in drive_files.items():
        if k not in local_meta:
            drive_orphans.append({
                'rel_path': k,
                'drive_size': v['size'],
                'drive_duration': v['duration_seconds'],
                'mod_time': v['mod_time']
            })

    drive_missing = []
    for k, v in local_meta.items():
        if k not in drive_files:
            drive_missing.append({
                'rel_path': k,
                'meta_duration': v['duration_seconds']
            })

    drive_too_short = []
    for k, v in drive_files.items():
        if v['duration_seconds'] < 5.0:
            meta_d = local_meta.get(k, {}).get('duration_seconds', 0)
            local_d = local_files.get(k, {}).get('duration_seconds', 0)
            drive_too_short.append({
                'rel_path': k,
                'drive_duration': v['duration_seconds'],
                'drive_size': v['size'],
                'meta_duration': meta_d,
                'local_duration': local_d,
                'mod_time': v['mod_time']
            })

    size_mismatches = []
    perfect_matches = 0

    for k, v in drive_files.items():
        if k in local_meta and k in local_files:
            meta_d = local_meta[k]['duration_seconds']
            local_d = local_files[k]['duration_seconds']
            drive_d = v['duration_seconds']

            if abs(drive_d - local_d) > 1.0:
                size_mismatches.append({
                    'rel_path': k,
                    'drive_duration': drive_d,
                    'drive_size': v['size'],
                    'local_duration': local_d,
                    'local_size': local_files[k]['size'],
                    'meta_duration': meta_d,
                    'diff_seconds': round(drive_d - local_d, 2),
                    'mod_time': v['mod_time']
                })
            else:
                perfect_matches += 1

    (OUT_DIR / 'drive_orphans.jsonl').write_text(
        '\n'.join(json.dumps(x, ensure_ascii=False) for x in drive_orphans), encoding='utf-8'
    )
    (OUT_DIR / 'drive_missing.jsonl').write_text(
        '\n'.join(json.dumps(x, ensure_ascii=False) for x in drive_missing), encoding='utf-8'
    )
    (OUT_DIR / 'drive_too_short.jsonl').write_text(
        '\n'.join(json.dumps(x, ensure_ascii=False) for x in drive_too_short), encoding='utf-8'
    )
    (OUT_DIR / 'size_mismatches.jsonl').write_text(
        '\n'.join(json.dumps(x, ensure_ascii=False) for x in size_mismatches), encoding='utf-8'
    )

    print('\n' + '=' * 85)
    print('  KẾT QUẢ ĐỐI SOÁT 3 CHIỀU CHI TIẾT:')
    print('=' * 85)
    print(f'  1. Tổng số file trong Metadata:                 {len(local_meta):,} file')
    print(f'  2. Tổng số file thực tế trên Local:            {len(local_files):,} file')
    print(f'  3. Tổng số file thực tế trên Google Drive:     {len(drive_files):,} file')
    print('-' * 85)
    print(f'  Số file TRÙNG KHỚP HOÀN HẢO (Drive == Local):  {perfect_matches:,} file')
    print(f'  Số file LỆCH KÍCH THƯỚC (Drive != Local):      {len(size_mismatches):,} file')
    print(f'  Số file TRÊN DRIVE QUÁ NGẮN (< 5.0s):          {len(drive_too_short):,} file')
    print(f'  Số file RÁC/ORPHAN TRÊN DRIVE (thừa):         {len(drive_orphans):,} file')
    print(f'  Số file THIẾU TRÊN DRIVE (chưa upload):        {len(drive_missing):,} file')
    print('=' * 85)
    print(f'[+] Toàn bộ danh sách chi tiết đã được lưu tại: {OUT_DIR}')
    print(f'[+] Thời gian thực thi: {time.time() - t0:.1f}s')

if __name__ == '__main__':
    run_reconciliation()
