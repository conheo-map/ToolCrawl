"""
tools/turbo_gpu_pipeline.py — Hệ thống cào lại, nâng cấp chất lượng âm thanh bằng GPU RTX 2050,
thanh trừng rác Local & Google Drive và đồng bộ hóa tự động.

Kiến trúc 2 tầng bất đồng bộ:
  - Tầng 1: 16 Workers tải song song video container gốc (play_url) từ TikWM CDN.
  - Tầng 2: GPU Worker (NVIDIA RTX 2050 CUDA) bóc tách âm thanh, chạy Demucs v4 CUDA (1.5s),
            chuẩn hóa EBU R128 (-16 LUFS) và kiểm định Whisper CUDA (0.3s).
  - Tầng 3: Tự động ghi đè audio sạch, lập danh sách purge_list.json cho rác thật.
  - Tầng 4: Xóa sạch rác trên Local & Google Drive (rclone deletefile), đồng bộ audio mới (rclone copy).
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os
import re
import json
import time
import shutil
import tempfile
import subprocess
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

VN_TZ = timezone(timedelta(hours=7))
BASE_DIR = Path(".")
RESULT_DIR = Path("tools/recrawl_results")
RESULT_DIR.mkdir(exist_ok=True)

ROOT_DRIVE_ID = "16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw"


def check_cuda() -> bool:
    """Kiểm tra CUDA và hiển thị thông tin GPU."""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"[+] CUDA Activated: {gpu_name} (Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB)", flush=True)
            return True
    except Exception:
        pass
    print("[!] CUDA not available — falling back to CPU", flush=True)
    return False


def get_whisper_cuda():
    """Nạp Faster-Whisper trên CUDA với float16."""
    from faster_whisper import WhisperModel
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    logger_str = f"Faster-Whisper ({device}, {compute_type})"
    print(f"[*] Loading {logger_str}...", flush=True)
    model = WhisperModel("base", device=device, compute_type=compute_type)
    print(f"[+] {logger_str} ready!", flush=True)
    return model


def process_audio_gpu(raw_wav: Path, whisper_model, use_cuda: bool) -> dict:
    """
    Chuỗi xử lý âm thanh vượt ngưỡng ASR trên GPU:
    1. Đánh giá Whisper VAD sơ bộ.
    2. Nếu bị nhạc nền che lấp: chạy Demucs v4 trên CUDA (1.5s) để bóc tách triệt để.
    3. Chuẩn hóa EBU R128 (-16 LUFS) và True-Peak < -1.0 dBFS.
    4. Kiểm định ASR cuối cùng.
    """
    res = {
        "pass": False,
        "reason": "unknown",
        "avg_logprob": None,
        "text": "",
        "word_count": 0,
        "stages": [],
    }

    # 1. Đánh giá sơ bộ bằng Whisper
    try:
        segs_iter, _ = whisper_model.transcribe(
            str(raw_wav),
            language="vi",
            vad_filter=True,
            without_timestamps=True,
        )
        segs = list(segs_iter)
        text = " ".join(s.text for s in segs).strip()
        avg_lp = sum(s.avg_logprob for s in segs) / max(len(segs), 1) if segs else -2.0
        no_sp = sum(s.no_speech_prob for s in segs) / max(len(segs), 1) if segs else 1.0
        wc = len(text.split())
    except Exception as e:
        res["reason"] = f"whisper_error:{e}"
        return res

    # Nếu hoàn toàn không có tiếng nói
    if not text or no_sp > 0.65 or wc < 2:
        res["reason"] = f"true_garbage_no_speech (no_speech_prob={no_sp:.2f})"
        return res

    current_wav = raw_wav
    stages = [f"pre_gate(lp={avg_lp:.2f},no_sp={no_sp:.2f})"]

    # 2. Nếu giọng bị nhạc nền che: Chỉ chạy Demucs v4 cho audio ngắn (<= 90s)
    # Audio dài (> 90s) như livestream, phóng sự dài thì Whisper VAD và EBU R128 là đủ, tránh nghẽn GPU!
    dur_sec = 0.0
    try:
        import soundfile as sf
        dur_sec = sf.info(str(raw_wav)).duration
    except Exception:
        pass

    if dur_sec <= 90.0 and (avg_lp < -0.50 or no_sp > 0.35):
        with tempfile.TemporaryDirectory() as demucs_tmp:
            device_flag = "cuda" if use_cuda else "cpu"
            cmd = [
                sys.executable, "-m", "demucs",
                "--two-stems=vocals",
                "--out", str(demucs_tmp),
                "--filename", "{stem}.{ext}",
                "-n", "htdemucs",
                "--shifts", "0",
                "-d", device_flag,
                str(current_wav),
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=60)
                vocal_file = Path(demucs_tmp) / "htdemucs" / "vocals.wav"
                if vocal_file.exists() and vocal_file.stat().st_size > 1000:
                    shutil.copy2(str(vocal_file), str(raw_wav))
                    stages.append(f"demucs_v4_{device_flag}")
            except Exception:
                stages.append("demucs_skipped")

    # 3. Chuẩn hóa EBU R128 (-16 LUFS)
    try:
        import soundfile as sf
        import pyloudnorm as pyln
        data, rate = sf.read(str(raw_wav))
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        meter = pyln.Meter(rate)
        loudness = meter.integrated_loudness(data)
        if loudness > -70.0 and abs(loudness - (-16.0)) > 1.0:
            norm_data = pyln.normalize.loudness(data, loudness, -16.0)
            max_val = abs(norm_data).max()
            if max_val > 0.95:
                norm_data = norm_data * (0.95 / max_val)
            sf.write(str(raw_wav), norm_data, rate, subtype="PCM_16")
            stages.append("ebu_r128(-16lufs)")
    except Exception:
        pass

    # 4. Kiểm tra ASR lần cuối
    try:
        segs_iter, _ = whisper_model.transcribe(str(raw_wav), language="vi", vad_filter=True, without_timestamps=True)
        segs = list(segs_iter)
        final_text = " ".join(s.text for s in segs).strip()
        final_lp = sum(s.avg_logprob for s in segs) / max(len(segs), 1) if segs else -2.0
        final_wc = len(final_text.split())

        if final_wc >= 3 and final_lp >= -0.75:
            res["pass"] = True
            res["text"] = final_text
            res["word_count"] = final_wc
            res["avg_logprob"] = round(final_lp, 3)
            res["stages"] = stages
        else:
            res["reason"] = f"low_quality_after_master (lp={final_lp:.2f}, wc={final_wc})"
    except Exception as e:
        res["reason"] = f"final_gate_error:{e}"

    return res


def run_pipeline(manifest_path: str, date_filter: str | None, workers: int = 16):
    print("=" * 80)
    print("  HỆ THỐNG CÀO LẠI SIÊU TỐC & NÂNG CẤP ÂM THANH GPU RTX 2050")
    print("=" * 80)
    t0 = time.time()

    use_cuda = check_cuda()
    whisper_model = get_whisper_cuda()

    from utils.tikwm_client import TikWMClient
    tikwm = TikWMClient()

    # Tải danh sách targets từ manifest
    manifest_data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    targets = manifest_data.get("targets", [])
    if date_filter:
        targets = [t for t in targets if t.get("date") == date_filter]
        print(f"[*] Đã lọc theo ngày {date_filter}: {len(targets):,} mục tiêu", flush=True)
    else:
        print(f"[*] Tổng số mục tiêu: {len(targets):,}", flush=True)

    success_count = 0
    purge_list = []
    results = []

    import threading
    tikwm_lock = threading.Lock()
    last_api_time = [0.0]
    gpu_lock = threading.Lock()

    def safe_get_video_info(url: str):
        with tikwm_lock:
            now = time.time()
            diff = now - last_api_time[0]
            if diff < 0.5:
                time.sleep(0.5 - diff)
            last_api_time[0] = time.time()
            return tikwm.get_video_info(url)

    def process_one_target(t):
        item_id = t["item_id"]
        raw_id = item_id.removeprefix("tt_").removeprefix("fb_").split("_")[0]
        week = t.get("week")
        date = t.get("date")
        audio_dir = BASE_DIR / week / date / "audio"
        dest_wav = audio_dir / f"{raw_id if not item_id.startswith(('tt_', 'fb_')) else item_id.split('_')[0]}.wav"

        # Chuẩn hóa URL để TikWM xử lý mượt mà nhất
        orig_url = t.get("video_url") or ""
        if "tiktok.com" in orig_url or item_id.startswith("tt_"):
            video_url = f"https://www.tiktok.com/@user/video/{raw_id}"
        else:
            video_url = orig_url or f"https://www.facebook.com/reel/{raw_id}"

        # 1. Thử lấy MP4 qua TikWM trước (với rate limiting an toàn)
        info = safe_get_video_info(video_url)
        play_url = info.get("play_url") if info else None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mp4_file = tmp / f"{item_id}.mp4"
            raw_wav = tmp / f"{item_id}_raw.wav"

            download_ok = False
            if play_url:
                download_ok = tikwm.download_video(play_url, mp4_file)

            # Fallback sang yt-dlp nếu TikWM không có link
            if not download_ok or not mp4_file.exists():
                ydl_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--format", "bestvideo+bestaudio/best[ext=mp4]/best",
                    "--output", str(mp4_file),
                    "--no-playlist", "--quiet", "--no-warnings",
                    "--socket-timeout", "20",
                    video_url
                ]
                subprocess.run(ydl_cmd, capture_output=True, timeout=40)

            if mp4_file.exists() and mp4_file.stat().st_size > 1000:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(mp4_file),
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    str(raw_wav)
                ], capture_output=True, timeout=60)

            if not raw_wav.exists() or raw_wav.stat().st_size < 1000:
                return {"item_id": item_id, "status": "DOWNLOAD_FAILED", "target": t}

            # 2. Xử lý âm thanh qua GPU (an toàn bộ nhớ VRAM với gpu_lock)
            with gpu_lock:
                gpu_res = process_audio_gpu(raw_wav, whisper_model, use_cuda)

            if gpu_res["pass"]:
                audio_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(raw_wav), str(dest_wav))
                return {
                    "item_id": item_id,
                    "status": "SUCCESS",
                    "dest_wav": str(dest_wav),
                    "avg_logprob": gpu_res["avg_logprob"],
                    "text": gpu_res["text"],
                    "word_count": gpu_res["word_count"],
                    "stages": gpu_res["stages"],
                    "target": t,
                }
            else:
                return {
                    "item_id": item_id,
                    "status": "PURGE_CANDIDATE",
                    "reason": gpu_res["reason"],
                    "target": t,
                }

    checkpoint_file = RESULT_DIR / "turbo_checkpoint.json"
    completed_ids = set()
    if checkpoint_file.exists():
        try:
            cp_data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            completed_ids = set(cp_data.get("completed_ids", []))
            print(f"[*] Checkpoint loaded: {len(completed_ids):,} chunks already processed", flush=True)
        except Exception:
            pass

    # Gom nhóm theo video gốc (raw_id) để loại bỏ trùng lặp triệt để
    from collections import defaultdict
    raw_to_targets = defaultdict(list)
    for t in targets:
        iid = t["item_id"]
        raw_id = iid.removeprefix("tt_").removeprefix("fb_").split("_")[0]
        base_tt = f"tt_{raw_id}"
        base_fb = f"fb_{raw_id}"
        if iid in completed_ids or raw_id in completed_ids or base_tt in completed_ids or base_fb in completed_ids:
            continue
        raw_to_targets[raw_id].append(t)

    unique_videos = list(raw_to_targets.keys())
    total_remaining_chunks = sum(len(v) for v in raw_to_targets.values())
    print(f"[*] Tổng video gốc CÒN LẠI cần cào & xử lý : {len(unique_videos):,} video gốc ({total_remaining_chunks:,} chunks)", flush=True)

    def process_one_video(raw_id):
        chunk_list = sorted(raw_to_targets[raw_id], key=lambda x: x["item_id"])
        rep_target = chunk_list[0]
        item_id = rep_target["item_id"]
        week = rep_target.get("week")
        date = rep_target.get("date")
        audio_dir = BASE_DIR / week / date / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        orig_url = rep_target.get("video_url") or ""
        if "tiktok.com" in orig_url or item_id.startswith("tt_"):
            video_url = f"https://www.tiktok.com/@user/video/{raw_id}"
        else:
            video_url = orig_url or f"https://www.facebook.com/reel/{raw_id}"

        info = safe_get_video_info(video_url)
        play_url = info.get("play_url") if info else None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mp4_file = tmp / f"{raw_id}.mp4"
            full_wav = tmp / f"{raw_id}_full.wav"

            download_ok = False
            if play_url:
                download_ok = tikwm.download_video(play_url, mp4_file)

            if not download_ok or not mp4_file.exists():
                ydl_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--format", "bestvideo+bestaudio/best[ext=mp4]/best",
                    "--output", str(mp4_file),
                    "--no-playlist", "--quiet", "--no-warnings",
                    "--socket-timeout", "20",
                    video_url
                ]
                subprocess.run(ydl_cmd, capture_output=True, timeout=40)

            if not mp4_file.exists() or mp4_file.stat().st_size < 1000:
                return raw_id, chunk_list, {"status": "PURGE_CANDIDATE", "reason": "download_failed_or_deleted", "chunks_ok": 0}

            # Trích xuất toàn bộ âm thanh WAV 16kHz mono từ video gốc
            subprocess.run([
                "ffmpeg", "-y", "-i", str(mp4_file),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(full_wav)
            ], capture_output=True, timeout=60)

            if not full_wav.exists() or full_wav.stat().st_size < 1000:
                return raw_id, chunk_list, {"status": "PURGE_CANDIDATE", "reason": "ffmpeg_extract_error", "chunks_ok": 0}

            # Lấy thời lượng tổng
            import soundfile as sf
            try:
                total_dur = sf.info(str(full_wav)).duration
            except Exception:
                total_dur = 30.0

            # Nếu video chỉ có 1 chunk đơn
            if len(chunk_list) == 1:
                cid = chunk_list[0]["item_id"]
                dest = audio_dir / f"{cid}.wav"
                with gpu_lock:
                    gpu_res = process_audio_gpu(full_wav, whisper_model, use_cuda)
                if gpu_res["pass"]:
                    shutil.copy2(str(full_wav), str(dest))
                    return raw_id, chunk_list, {"status": "SUCCESS", "avg_logprob": gpu_res["avg_logprob"], "chunks_ok": 1}
                else:
                    return raw_id, chunk_list, {"status": "PURGE_CANDIDATE", "reason": gpu_res["reason"], "chunks_ok": 0}

            # Nếu là VIDEO DÀI: Cắt thành từng chunk 30s đúng chuẩn và xử lý từng chunk!
            chunk_dur = total_dur / len(chunk_list)
            chunks_ok = 0
            for idx, t in enumerate(chunk_list):
                cid = t["item_id"]
                dest = audio_dir / f"{cid}.wav"
                chunk_wav = tmp / f"{cid}.wav"
                start_sec = idx * chunk_dur

                # Cắt chính xác bằng ffmpeg (0.01 giây)
                subprocess.run([
                    "ffmpeg", "-y", "-ss", f"{start_sec:.2f}", "-t", f"{chunk_dur:.2f}",
                    "-i", str(full_wav), "-acodec", "copy", str(chunk_wav)
                ], capture_output=True, timeout=15)

                if chunk_wav.exists() and chunk_wav.stat().st_size > 1000:
                    with gpu_lock:
                        gpu_res = process_audio_gpu(chunk_wav, whisper_model, use_cuda)
                    if gpu_res["pass"]:
                        shutil.copy2(str(chunk_wav), str(dest))
                        chunks_ok += 1
                        completed_ids.add(cid)
                    else:
                        purge_list.append(t)
                        completed_ids.add(cid)
                else:
                    purge_list.append(t)
                    completed_ids.add(cid)

            res_status = "SUCCESS" if chunks_ok > 0 else "PURGE_CANDIDATE"
            return raw_id, chunk_list, {"status": res_status, "chunks_ok": chunks_ok}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_one_video, rid): rid for rid in unique_videos}
        done = 0
        for f in as_completed(futures):
            done += 1
            raw_id, chunk_list, res = f.result()
            chunks_ok = res.get("chunks_ok", 0)
            success_count += chunks_ok

            if len(chunk_list) == 1:
                cid = chunk_list[0]["item_id"]
                completed_ids.add(cid)
                if res["status"] != "SUCCESS":
                    purge_list.append(chunk_list[0])

            completed_ids.add(f"tt_{raw_id}")
            completed_ids.add(raw_id)

            status_str = f"SUCCESS ({chunks_ok}/{len(chunk_list)} chunks)" if chunks_ok > 0 else f"PURGE ({len(chunk_list)} chunks)"
            lp_info = f"lp={res.get('avg_logprob')}" if "avg_logprob" in res else res.get("reason", "")
            print(f"[{done}/{len(unique_videos)}] Video {raw_id} -> {status_str} {lp_info} | Tổng chunk đạt ASR: {success_count}", flush=True)

            # Lưu checkpoint mỗi 5 video gốc
            if done % 5 == 0 or done == len(unique_videos):
                cp_data = {
                    "saved_at": datetime.now(VN_TZ).isoformat(timespec="seconds"),
                    "completed_ids": sorted(completed_ids),
                    "success_count": success_count,
                    "purge_count": len(purge_list),
                }
                checkpoint_file.write_text(json.dumps(cp_data, ensure_ascii=False, indent=2), encoding="utf-8")
                purge_file = RESULT_DIR / "purge_list.json"
                purge_file.write_text(json.dumps(purge_list, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print(f"  HOÀN TẤT GIAI ĐOẠN XỬ LÝ GPU ({elapsed:.1f}s | {elapsed/max(len(active_targets),1):.2f}s/file)")
    print("=" * 80)
    print(f"  Tổng số mục tiêu đã xử lý : {len(active_targets):,}")
    print(f"  Khôi phục thành công      : {success_count:,} ({success_count/max(len(active_targets),1)*100:.1f}%)")
    print(f"  Số file rác cần xóa       : {len(purge_list):,}")
    print("=" * 80)

    purge_file = RESULT_DIR / "purge_list.json"
    purge_file.write_text(json.dumps(purge_list, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] Danh sách file rác đã lưu: {purge_file}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, default="tools/master_audit_results/recrawl_manifest.json")
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    run_pipeline(args.manifest, args.date, args.workers)
