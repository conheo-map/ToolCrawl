"""
tools/batch_gpu_transcribe.py — Triển khai Phương án 2.1:
Dùng GPU NVIDIA RTX 2050 chạy Faster-Whisper trích xuất transcript tiếng Việt
cho toàn bộ các file âm thanh sạch còn thiếu nhãn của Week2 và Week3.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os
import json
import time
import torch
from pathlib import Path
from faster_whisper import WhisperModel

BASE_DIR = Path(".")
CHECKPOINT_DIR = BASE_DIR / ".checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = CHECKPOINT_DIR / "transcribe_progress.jsonl"
MANIFEST_FILE = BASE_DIR / "tools" / "asr_training_corpus" / "data_manifest_asr_train.jsonl"
MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)

def run_transcribe():
    print("=" * 85)
    print("  GIAI ĐOẠN 2: GPU FASTER-WHISPER TRANSCRIBE (PHƯƠNG ÁN 2.1)")
    print("=" * 85)
    t0 = time.time()

    # 1. Nạp các file đã transcribe từ checkpoint
    done_ids = set()
    if PROGRESS_FILE.exists():
        for line in PROGRESS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done_ids.add(json.loads(line)["item_id"])
                except Exception:
                    pass
    print(f"[*] Checkpoint hiện tại: đã transcribe xong {len(done_ids):,} file.")

    # 2. Nạp manifest hiện có
    manifest_map = {}
    if MANIFEST_FILE.exists():
        for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    obj = json.loads(line)
                    stem = Path(obj["audio_filepath"]).stem
                    text = obj.get("text", "").strip()
                    if len(text.split()) >= 3:
                        manifest_map[stem] = text
                        done_ids.add(stem)
                except Exception:
                    pass
    print(f"[*] Manifest hiện tại: đã có {len(manifest_map):,} transcript hợp lệ (>= 3 từ).")

    # 3. Quét toàn bộ file audio sạch trên đĩa cần transcribe
    todo_files = [] # list of (item_id, wav_path, rel_meta_path, duration)
    for mf in sorted(list(BASE_DIR.glob("Week*/*/metadata.json"))):
        d = mf.parent
        audio_dir = d / "audio"
        recs = json.loads(mf.read_text(encoding="utf-8"))
        for r in recs:
            iid = r["item_id"]
            wav_path = audio_dir / f"{iid}.wav"
            if wav_path.exists() and iid not in done_ids:
                dur = r.get("duration_seconds", 30.0)
                rel_meta = f"audio/{d.name}/{iid}.wav"
                todo_files.append((iid, wav_path, rel_meta, dur))

    print(f"[*] Tổng số file sạch cần transcribe trên GPU: {len(todo_files):,} file ({sum(f[3] for f in todo_files)/3600:.2f} giờ).")

    if not todo_files:
        print("[+] TOÀN BỘ CÁC FILE ĐÃ ĐƯỢC TRANSCRIBE ĐẦY ĐỦ! 100% ASR-READY!")
        return

    # 4. Khởi tạo mô hình Faster-Whisper trên GPU CUDA float16
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"\n[*] Đang khởi tạo Faster-Whisper ({device}, {compute_type})...")
    model = WhisperModel("base", device=device, compute_type=compute_type)
    print("[+] Model Faster-Whisper đã sẵn sàng trên GPU!\n")

    # 5. Tiến hành transcribe theo batch với checkpoint tức thì
    success_count = 0
    total_audio_processed = 0.0

    with open(PROGRESS_FILE, "a", encoding="utf-8") as f_prog, open(MANIFEST_FILE, "a", encoding="utf-8") as f_man:
        for idx, (iid, wav_path, rel_meta, dur) in enumerate(todo_files, 1):
            try:
                segments, info = model.transcribe(str(wav_path), language="vi", beam_size=1)
                text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()

                record = {
                    "item_id": iid,
                    "text": text,
                    "word_count": len(text.split()),
                    "duration_seconds": round(dur, 2)
                }
                f_prog.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_prog.flush()

                # Ghi vào manifest chuẩn ASR
                manifest_entry = {
                    "audio_filepath": rel_meta,
                    "duration": round(dur, 2),
                    "text": text
                }
                f_man.write(json.dumps(manifest_entry, ensure_ascii=False) + "\n")
                f_man.flush()

                success_count += 1
                total_audio_processed += dur

                if idx % 50 == 0 or idx == len(todo_files):
                    elapsed = time.time() - t0
                    speed_fps = idx / elapsed
                    eta_sec = (len(todo_files) - idx) / speed_fps if speed_fps > 0 else 0
                    print(f"[{idx:,}/{len(todo_files):,}] ({idx/len(todo_files)*100:.1f}%) "
                          f"Đã xử lý: {total_audio_processed/3600:.2f}h audio | "
                          f"Tốc độ: {speed_fps:.2f} file/s | "
                          f"Còn lại: ~{eta_sec/60:.1f} phút", flush=True)

            except Exception as exc:
                print(f"  [-] Lỗi file {iid}: {exc}", flush=True)

    print("\n" + "=" * 85)
    print(f"  HOÀN TẤT GIAI ĐOẠN 2: ĐÃ TRANSCRIBE THÀNH CÔNG {success_count:,} FILE ({total_audio_processed/3600:.2f}h) TRONG {time.time()-t0:.1f}s")
    print("=" * 85)

if __name__ == "__main__":
    run_transcribe()
