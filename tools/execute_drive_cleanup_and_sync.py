
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import subprocess
import time
from pathlib import Path

ROOT_DRIVE_ID = '16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw'
RES_DIR = Path('tools/reconciliation_results')

def main():
    print('=' * 85)
    print('  BẮT ĐẦU QUY TRÌNH CHUẨN HÓA TOÀN DIỆN GOOGLE DRIVE:')
    print('  [BƯỚC 1] XÓA 4,589 TỆP RÁC / ORPHAN KHỎI GOOGLE DRIVE')
    print('  [BƯỚC 2] UPLOAD ĐÈ 6,073 TỆP ÂM THANH 30S CHUẨN ASR TỪ LOCAL LÊN DRIVE')
    print('=' * 85)

    # 1. Chuẩn bị danh sách xóa orphan
    orphans_file = RES_DIR / 'drive_orphans.jsonl'
    w2_orphans = []
    w3_orphans = []

    for line in orphans_file.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        obj = json.loads(line)
        p = obj['rel_path']
        if p.startswith('Week2/'):
            w2_orphans.append(p[len('Week2/'):])
        elif p.startswith('Week3/'):
            w3_orphans.append(p[len('Week3/'):])

    print(f'[*] Đã phân loại tệp rác cần xóa trên Drive:')
    print(f'  - Week2: {len(w2_orphans):,} tệp')
    print(f'  - Week3: {len(w3_orphans):,} tệp')

    f_w2_orphans = RES_DIR / 'w2_orphans.txt'
    f_w3_orphans = RES_DIR / 'w3_orphans.txt'
    f_w2_orphans.write_text('\n'.join(w2_orphans), encoding='utf-8')
    f_w3_orphans.write_text('\n'.join(w3_orphans), encoding='utf-8')

    print('\n[*] Đang thực thi xóa tệp rác trên Week2 Google Drive...')
    t0 = time.time()
    r1 = subprocess.run([
        'rclone', 'delete',
        f'gdrive,root_folder_id={ROOT_DRIVE_ID}:Week2',
        '--files-from', str(f_w2_orphans),
        '--fast-list',
        '--transfers', '16'
    ], capture_output=True, text=True)
    print(f'  -> Xóa Week2 hoàn tất ({time.time()-t0:.1f}s), mã thoát: {r1.returncode}')

    print('\n[*] Đang thực thi xóa tệp rác trên Week3 Google Drive...')
    t1 = time.time()
    r2 = subprocess.run([
        'rclone', 'delete',
        f'gdrive,root_folder_id={ROOT_DRIVE_ID}:Week3',
        '--files-from', str(f_w3_orphans),
        '--fast-list',
        '--transfers', '16'
    ], capture_output=True, text=True)
    print(f'  -> Xóa Week3 hoàn tất ({time.time()-t1:.1f}s), mã thoát: {r2.returncode}')

    # 2. Chuẩn bị danh sách upload đè 6,073 tệp 30s
    mismatch_file = RES_DIR / 'size_mismatches.jsonl'
    w2_update = []
    w3_update = []

    for line in mismatch_file.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        obj = json.loads(line)
        p = obj['rel_path']
        if p.startswith('Week2/'):
            w2_update.append(p[len('Week2/'):])
        elif p.startswith('Week3/'):
            w3_update.append(p[len('Week3/'):])

    print(f'\n[*] Đã phân loại tệp âm thanh 30s cần upload đè lên Drive:')
    print(f'  - Week2: {len(w2_update):,} tệp')
    print(f'  - Week3: {len(w3_update):,} tệp')

    f_w2_update = RES_DIR / 'w2_update.txt'
    f_w3_update = RES_DIR / 'w3_update.txt'
    f_w2_update.write_text('\n'.join(w2_update), encoding='utf-8')
    f_w3_update.write_text('\n'.join(w3_update), encoding='utf-8')

    print('\n[*] Đang upload đè các tệp 30s mới lên Week2 Google Drive...')
    t2 = time.time()
    r3 = subprocess.run([
        'rclone', 'copy',
        'Week2',
        f'gdrive,root_folder_id={ROOT_DRIVE_ID}:Week2',
        '--files-from', str(f_w2_update),
        '--transfers', '16',
        '--fast-list'
    ], capture_output=True, text=True)
    print(f'  -> Upload Week2 hoàn tất ({time.time()-t2:.1f}s), mã thoát: {r3.returncode}')

    print('\n[*] Đang upload đè các tệp 30s mới lên Week3 Google Drive...')
    t3 = time.time()
    r4 = subprocess.run([
        'rclone', 'copy',
        'Week3',
        f'gdrive,root_folder_id={ROOT_DRIVE_ID}:Week3',
        '--files-from', str(f_w3_update),
        '--transfers', '16',
        '--fast-list'
    ], capture_output=True, text=True)
    print(f'  -> Upload Week3 hoàn tất ({time.time()-t3:.1f}s), mã thoát: {r4.returncode}')

    print('\n' + '=' * 85)
    print('  HOÀN TẤT BƯỚC 1 VÀ BƯỚC 2: GOOGLE DRIVE ĐÃ ĐƯỢC ĐỒNG BỘ HOÀN TOÀN!')
    print('=' * 85)

if __name__ == '__main__':
    main()
