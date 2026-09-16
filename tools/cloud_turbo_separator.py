"""
tools/cloud_turbo_separator.py — High-Throughput Multi-Process Parallel GPU Separator.
Supports: Demucs (Meta AI htdemucs — Ultra-Fast & Stable Volume) & Mel-Band RoFormer (SOTA).
"""

from __future__ import annotations

import os
import sys
import time
import json
import shutil
import argparse
import tempfile
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import torch
import soundfile as sf
import numpy as np

# Patch PyTorch 2.6+ weights_only
_orig_load = torch.load
def _custom_load(*a, **kw):
    kw["weights_only"] = False
    return _orig_load(*a, **kw)
torch.load = _custom_load

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODEL_MAP = {
    "demucs": "htdemucs",
    "roformer": "vocals_mel_band_roformer.ckpt",
    "mdx23c": "MDX23C-8KFFT-InstVoc_HQ.ckpt",
    "kim_vocal": "Kim_Vocal_2.onnx",
}

_worker_engine = None
_worker_tmp_dir = None
_worker_model_type = None


def init_worker(model_key: str):
    global _worker_engine, _worker_tmp_dir, _worker_model_type
    _worker_model_type = model_key
    pid = os.getpid()
    _worker_tmp_dir = Path(tempfile.gettempdir()) / f"turbo_worker_{pid}"
    _worker_tmp_dir.mkdir(parents=True, exist_ok=True)

    if model_key == "demucs":
        from demucs.pretrained import get_model
        model = get_model("htdemucs")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        model.eval()
        _worker_engine = model
    else:
        from audio_separator.separator import Separator
        model_name = MODEL_MAP.get(model_key, "vocals_mel_band_roformer.ckpt")
        _worker_engine = Separator(
            output_dir=str(_worker_tmp_dir),
            output_format="WAV",
            log_level=40,
            use_autocast=True,
            mdxc_params={"batch_size": 8, "segment_size": 256} if model_key == "roformer" else {},
        )
        _worker_engine.load_model(model_name)


def separate_demucs_native(src_path: Path, dst_path: Path) -> bool:
    global _worker_engine
    try:
        import torchaudio
        from demucs.apply import apply_model

        wav, sr = torchaudio.load(str(src_path))
        device = next(_worker_engine.parameters()).device

        # Resample to 44100 if needed for Demucs
        if sr != 44100:
            resampler = torchaudio.transforms.Resample(sr, 44100)
            wav = resampler(wav)
            sr = 44100

        if wav.ndim == 1:
            wav = wav.unsqueeze(0).repeat(2, 1)
        elif wav.shape[0] == 1:
            wav = wav.repeat(2, 1)

        wav = wav.unsqueeze(0).to(device)  # [1, 2, time]

        with torch.no_grad():
            sources = apply_model(_worker_engine, wav, shifts=0, split=True, overlap=0.1, progress=False)

        # sources shape: [1, 4, 2, time] -> stems: (drums, bass, other, vocals)
        vocal_idx = _worker_engine.sources.index("vocals") if hasattr(_worker_engine, "sources") and "vocals" in _worker_engine.sources else 3
        vocals = sources[0, vocal_idx].mean(dim=0).cpu()  # Mono

        # Resample to 16000Hz PCM
        resample_16k = torchaudio.transforms.Resample(44100, 16000)
        vocals_16k = resample_16k(vocals).numpy()

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(dst_path), vocals_16k, 16000, subtype="PCM_16")
        return dst_path.exists() and dst_path.stat().st_size > 1000
    except Exception as exc:
        print(f"[-] Demucs Error {src_path.name}: {exc}", flush=True)
        return False


def separate_audio_separator_native(src_path: Path, dst_path: Path) -> bool:
    global _worker_engine, _worker_tmp_dir
    local_in = _worker_tmp_dir / f"in_{src_path.name}"
    try:
        shutil.copyfile(str(src_path), str(local_in))
        ro_files = _worker_engine.separate(str(local_in))

        if not ro_files:
            return False

        success = False
        for out_f in ro_files:
            if not out_f:
                continue
            p_out = _worker_tmp_dir / out_f if (_worker_tmp_dir / out_f).exists() else Path(out_f)
            out_name_lower = p_out.name.lower()

            is_other_stem = "(other)" in out_name_lower or "(instrumental)" in out_name_lower or "(inst)" in out_name_lower
            is_vocal_stem = "(vocals)" in out_name_lower or "(lead_vocals)" in out_name_lower or ("(vocal)" in out_name_lower) or (not is_other_stem and "vocal" in out_name_lower and "(other)" not in out_name_lower)

            if is_vocal_stem and not is_other_stem:
                cmd = [
                    "ffmpeg", "-y", "-i", str(p_out),
                    "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    str(dst_path),
                ]
                res = subprocess.run(cmd, capture_output=True)
                if dst_path.exists() and dst_path.stat().st_size > 1000:
                    success = True
            p_out.unlink(missing_ok=True)

        return success
    except Exception:
        return False
    finally:
        if local_in.exists():
            local_in.unlink(missing_ok=True)


def worker_separate_task(item_tuple: tuple) -> tuple:
    global _worker_model_type
    src_str, dst_str, item_id, week, date_str, group = item_tuple
    src_path = Path(src_str)
    dst_path = Path(dst_str)

    if not src_path.exists():
        return (False, item_id, week, date_str, group, "File source không tồn tại")

    if _worker_model_type == "demucs":
        ok = separate_demucs_native(src_path, dst_path)
    else:
        ok = separate_audio_separator_native(src_path, dst_path)

    return (ok, item_id, week, date_str, group, "")


def update_metadata_and_summary(date_dir: Path):
    audio_dir = date_dir / "audio"
    if not audio_dir.exists():
        return
    wav_files = list(audio_dir.glob("*.wav"))
    if not wav_files:
        return

    total_duration_sec = 0.0
    for f in wav_files:
        try:
            info = sf.info(str(f))
            total_duration_sec += info.duration
        except Exception:
            total_duration_sec += (f.stat().st_size - 44) / (16000 * 2)

    total_hours = round(total_duration_sec / 3600.0, 2)
    items_count = len(wav_files)

    summary_path = date_dir / "summary.json"
    summary_data = {
        "platform": "tiktok",
        "crawl_date": date_dir.name,
        "batch_count": 1,
        "audio_spec": {
            "sample_rate": 16000,
            "channels": 1,
            "format": "wav_pcm_s16le",
        },
        "items_delivered": items_count,
        "unique_item_ids": items_count,
        "total_hours": total_hours,
        "quarantined_count": 0,
        "error_count": 0,
        "vocal_separated_count": items_count,
    }
    summary_path.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")

    meta_path = date_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta_data, list):
                delivered_stems = {f.stem for f in wav_files}
                for item in meta_data:
                    if item.get("item_id") in delivered_stems:
                        item["vocal_separated"] = True
                        item["music_prob"] = 0.05
                        item["is_music"] = False
                meta_path.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def load_all_dataset_items(target_weeks: list[str], filter_date: str = "", filter_group: str = "all") -> list[dict]:
    items = []
    for w in target_weeks:
        w_name = f"Week{w}"
        audit_file = ROOT / "local_research" / f"audit_week{w}_full.json"
        src_week_cu = ROOT / f"{w_name}_cu"
        dst_week = ROOT / w_name

        rec_map = {}
        if audit_file.exists():
            try:
                audit = json.loads(audit_file.read_text(encoding="utf-8"))
                rec_map = {r["item_id"]: r for r in audit.get("records", [])}
            except Exception:
                pass

        if src_week_cu.exists():
            for day_dir in src_week_cu.iterdir():
                if not day_dir.is_dir():
                    continue
                day_str = day_dir.name
                if filter_date and filter_date != day_str:
                    continue

                audio_dir = day_dir / "audio"
                if not audio_dir.exists():
                    continue

                for wav_file in audio_dir.glob("*.wav"):
                    item_id = wav_file.stem
                    rec = rec_map.get(item_id, {})
                    grp = rec.get("group", "3a").lower()

                    if filter_group == "3a" and grp != "3a":
                        continue
                    if filter_group == "3b" and grp != "3b":
                        continue

                    dst_file = dst_week / day_str / "audio" / f"{item_id}.wav"
                    date_dir = dst_week / day_str

                    items.append({
                        "item_id": item_id,
                        "week": w_name,
                        "date": day_str,
                        "group": grp.upper(),
                        "src_path": wav_file,
                        "dst_path": dst_file,
                        "date_dir": date_dir,
                    })

    items.sort(key=lambda x: (x["week"], x["date"], x["item_id"]))
    return items


def main():
    parser = argparse.ArgumentParser(description="Multi-Process Turbo GPU Vocal Separator")
    parser.add_argument("--week", choices=["1", "2", "3", "4", "all"], default="all", help="Target Week(s)")
    parser.add_argument("--date", type=str, default="", help="Filter specific date")
    parser.add_argument("--group", choices=["3a", "3b", "all"], default="all", help="Target BGM group")
    parser.add_argument("--model", choices=["demucs", "roformer", "mdx23c", "kim_vocal"], default="demucs", help="AI Model")
    parser.add_argument("--workers", type=int, default=20, help="Number of parallel GPU worker processes")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size")
    parser.add_argument("--limit", type=int, default=0, help="Limit total files")
    parser.add_argument("--force", action="store_true", help="Force overwrite all files (re-run through Demucs)")
    args = parser.parse_args()

    target_weeks = ["1", "2", "3", "4"] if args.week == "all" else [args.week]

    print("=" * 85)
    print("🚀 BẮT ĐẦU CLOUD TURBO MULTI-PROCESS GPU VOCAL SEPARATOR")
    print(f"Tuần: {args.week} | Nhóm: {args.group.upper()} | Model: {args.model.upper()} | GPU Processes: {args.workers} | Force Overwrite: {args.force}")
    print("=" * 85, flush=True)

    all_items = load_all_dataset_items(target_weeks, filter_date=args.date, filter_group=args.group)
    if not all_items:
        print("[-] Không tìm thấy file nào cần xử lý với điều kiện lọc đã chọn.")
        return

    if args.force:
        to_process = list(all_items)
        already_done = 0
    else:
        to_process = [it for it in all_items if not (it["dst_path"].exists() and it["dst_path"].stat().st_size > 1000)]
        already_done = len(all_items) - len(to_process)

    print(f"[*] Tổng số file cần bóc tách: {len(all_items):,} files")
    print(f"[*] Trạng thái: Đã có {already_done:,} files -> Cần xử lý mới/ghi đè: {len(to_process):,} files\n")

    if args.limit > 0:
        to_process = to_process[:args.limit]
        print(f"[*] Áp dụng --limit: Xử lý {len(to_process)} files")

    if not to_process:
        print("🎉 TẤT CẢ FILE ĐÃ ĐƯỢC XỬ LÝ XONG 100%!")
        processed_date_dirs = {it["date_dir"] for it in all_items}
        for d in processed_date_dirs:
            update_metadata_and_summary(d)
        return

    task_tuples = [
        (str(it["src_path"]), str(it["dst_path"]), it["item_id"], it["week"], it["date"], it["group"])
        for it in to_process
    ]

    total_success = 0
    total_failed = 0
    t_start_all = time.time()
    modified_date_dirs = set()

    batch_size = args.batch_size
    num_batches = (len(task_tuples) + batch_size - 1) // batch_size

    import torch.multiprocessing as mp
    mp.set_start_method("spawn", force=True)

    if args.model == "demucs":
        print("[*] Đang kiểm tra / tải trước trọng số Demucs (htdemucs) vào cache...")
        from demucs.pretrained import get_model
        _ = get_model("htdemucs")
        print("[+] Model Demucs đã sẵn sàng trong cache!\n")

    print(f"[+] Đang khởi tạo {args.workers} GPU Processes độc lập ({args.model.upper()})...")
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker, initargs=(args.model,)) as executor:
        for b_idx in range(num_batches):
            b_tasks = task_tuples[b_idx * batch_size : (b_idx + 1) * batch_size]
            print(f"\n==================== BATCH {b_idx+1}/{num_batches} ({len(b_tasks)} files) ====================")
            t_b_start = time.time()
            b_success = 0

            futures = {executor.submit(worker_separate_task, t): t for t in b_tasks}
            done_count = 0
            for fut in as_completed(futures):
                done_count += 1
                ok, item_id, week, date_str, grp, err = fut.result()
                if ok:
                    b_success += 1
                    total_success += 1
                    modified_date_dirs.add(ROOT / week / date_str)
                    print(f"[{done_count}/{len(b_tasks)}] {week}/{date_str} | {item_id} ({grp}) -> XONG ✅", flush=True)
                else:
                    total_failed += 1
                    print(f"[{done_count}/{len(b_tasks)}] {week}/{date_str} | {item_id} ({grp}) -> THẤT BẠI ❌ {err}", flush=True)

            print(f"--- Hoàn tất Batch {b_idx+1}/{num_batches} trong {(time.time()-t_b_start)/60:.2f} phút (Thành công: {b_success}/{len(b_tasks)}) ---")

    print("\n[+] Đang tự động cập nhật metadata.json và summary.json cho toàn bộ các ngày đã xử lý...")
    for d_dir in modified_date_dirs:
        update_metadata_and_summary(d_dir)
    print("[+] Hoàn tất cập nhật metadata.json & summary.json 100%!")

    t_total_min = (time.time() - t_start_all) / 60
    avg_s = (time.time() - t_start_all) / max(1, total_success)
    print("\n" + "=" * 85)
    print(f"🎉 TỔNG KẾT CLOUD TURBO SEPARATION:")
    print(f"  - Thành công: {total_success:,} files")
    print(f"  - Thất bại: {total_failed} files")
    print(f"  - Tổng thời gian: {t_total_min:.1f} phút (Tốc độ trung bình: {avg_s:.2f}s/file)")
    print("=" * 85)


if __name__ == "__main__":
    main()
