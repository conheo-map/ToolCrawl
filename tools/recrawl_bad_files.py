"""
tools/recrawl_bad_files.py — Cào lại các file audio lỗi bằng TikWM Engine mới.

Đầu vào:
  - File JSON từ detect_bad_files.py (danh sách bad_files với item_id + week + date)
  - HOẶC: file .txt chứa item_ids (tt_XXXX)

Quy trình:
  1. Đọc item_id → xác định ngày và thư mục lưu gốc (Week/Date/audio/)
  2. Gọi TikWM API → tải MP4 video thực sự
  3. Extract audio WAV từ container MP4 (FFmpeg)
  4. Chạy SpeechMaster 4 tầng → kiểm định chất lượng
  5. Ghi đè file WAV cũ bằng file mới (chỉ khi pass)
  6. Cập nhật metadata.json + summary.json trong thư mục ngày

Chạy: python tools/recrawl_bad_files.py --report tools/bad_files_report/bad_files_XXX.json [--workers 3] [--dry-run]
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
from utils.tikwm_client import TikWMClient
from processors.speech_master import SpeechMaster

logger = get_logger("recrawl_bad_files")
VN_TZ = timezone(timedelta(hours=7))

RESULT_DIR = Path("tools/recrawl_results")
RESULT_DIR.mkdir(exist_ok=True)
CHECKPOINT_FILE = RESULT_DIR / "recrawl_checkpoint.json"


def load_checkpoint() -> set[str]:
    """Tải danh sách các item_id đã cào lại thành công hoặc đã xử lý."""
    if CHECKPOINT_FILE.exists():
        try:
            d = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
            return set(d.get("completed_ids", []))
        except Exception:
            return set()
    return set()


def save_checkpoint(completed_ids: set[str], stats: dict):
    """Ghi checkpoint tiến độ atomic xuống đĩa."""
    try:
        data = {
            "updated_at": datetime.now(VN_TZ).isoformat(timespec="seconds"),
            "completed_count": len(completed_ids),
            "stats": stats,
            "completed_ids": sorted(completed_ids),
        }
        tmp = CHECKPOINT_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CHECKPOINT_FILE)
    except Exception:
        pass


def update_date_metadata(audio_dir: Path, base_item_id: str, new_duration: float, speech_quality: dict):
    """Cập nhật metadata.json trong thư mục ngày tương ứng với thông tin audio mới."""
    meta_path = audio_dir.parent / "metadata.json"
    if not meta_path.exists():
        return
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        updated = False
        for r in data:
            if r.get("item_id", "").startswith(base_item_id):
                r["duration_seconds"] = round(new_duration, 2)
                r["_speech_quality"] = speech_quality
                r["recrawled_at"] = datetime.now(VN_TZ).isoformat(timespec="seconds")
                updated = True
        if updated:
            tmp = meta_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(meta_path)
    except Exception as e:
        logger.debug(f"Failed to update metadata.json: {e}")


# ── Singleton SpeechMaster (Whisper model load 1 lần) ─────────────────────────
_sm_instance: SpeechMaster | None = None

def get_speech_master(use_demucs: bool | None = None) -> SpeechMaster:
    global _sm_instance
    if _sm_instance is None:
        import torch
        if use_demucs is None:
            use_demucs = torch.cuda.is_available()
        _sm_instance = SpeechMaster(
            enable_vocal_separation=True,
            enable_dereverb=True,
            enable_loudnorm=True,
            enable_asr_gate=True,
            use_demucs=use_demucs,
        )
    return _sm_instance


# ── Tìm đường dẫn file WAV gốc từ item_id ─────────────────────────────────────

def find_original_wav(item_id: str, base_dir: Path = Path(".")) -> tuple[Path | None, str | None, str | None]:
    """
    Tìm file WAV gốc và thư mục ngày của nó.
    Trả về (wav_path, week_name, date_str) hoặc (None, None, None).
    """
    for week_dir in sorted(base_dir.glob("Week*/")):
        for date_dir in sorted(week_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            wav = date_dir / "audio" / f"{item_id}.wav"
            if wav.exists():
                return wav, week_dir.name, date_dir.name
    return None, None, None


def build_tiktok_url(item_id: str) -> str:
    """
    Tạo URL TikTok từ item_id (dạng tt_VIDEOID hoặc tt_VIDEOID_NN nếu là slice).
    QUAN TRỌNG: Không thêm '@user/' vì TikWM sẽ tìm tài khoản 'user' và trả về code=-1.
    Dùng format trực tiếp: https://www.tiktok.com/video/{video_id}
    """
    import re
    # Bỏ prefix "tt_"
    raw = item_id.removeprefix("tt_")
    # Loại bỏ hậu tố slice: _01, _02, _03... (2 chữ số)
    raw = re.sub(r"_\d{2}$", "", raw)
    # Lấy chỉ phần số video ID
    m = re.search(r"(\d{8,19})", raw)
    if not m:
        return f"https://www.tiktok.com/video/{raw}"
    return f"https://www.tiktok.com/video/{m.group(1)}"


def get_base_item_id(item_id: str) -> str:
    """Trả về item_id gốc (bỏ hậu tố slice _NN nếu có)."""
    import re
    return re.sub(r"_\d{2}$", "", item_id)


def find_original_wav_dir(item_id: str, base_dir: Path = Path(".")) -> tuple[Path | None, str | None, str | None]:
    """
    Tìm thư mục audio gốc chứa file WAV liên quan đến item_id.
    Hỗ trợ cả item_id gốc (tt_VIDEOID) và item_id slice (tt_VIDEOID_NN).
    Trả về (audio_dir, week_name, date_str) hoặc (None, None, None).
    """
    base_id = get_base_item_id(item_id)

    for week_dir in sorted(base_dir.glob("Week*/")):
        for date_dir in sorted(week_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            audio_dir = date_dir / "audio"
            if not audio_dir.exists():
                continue
            # Tìm bất kỳ file nào bắt đầu bằng base_id
            matches = list(audio_dir.glob(f"{base_id}*.wav"))
            if matches:
                return audio_dir, week_dir.name, date_dir.name
    return None, None, None


_meta_cache = {}

def lookup_original_video_url(audio_dir: Path, item_id: str) -> str | None:
    """Đọc URL video gốc chuẩn từ metadata.json trong thư mục ngày để có đúng author username."""
    meta_path = audio_dir.parent / "metadata.json"
    if not meta_path.exists():
        return None
    
    if str(meta_path) not in _meta_cache:
        try:
            records = json.loads(meta_path.read_text(encoding="utf-8"))
            _meta_cache[str(meta_path)] = {r["item_id"]: r.get("video_url") for r in records if "item_id" in r}
        except Exception:
            _meta_cache[str(meta_path)] = {}
            
    cache = _meta_cache.get(str(meta_path), {})
    if item_id in cache and cache[item_id]:
        return cache[item_id]
    base_id = get_base_item_id(item_id)
    for k, v in cache.items():
        if k.startswith(base_id) and v:
            return v
    return None


def recrawl_one(item_id: str, date_hint: str | None, week_hint: str | None,
                video_url_hint: str | None = None,
                dry_run: bool = False) -> dict:
    """
    Cào lại 1 file audio lỗi bằng TikWM engine mới.
    Xử lý cả file gốc (tt_VIDEOID.wav) và file đã slice (tt_VIDEOID_NN.wav).
    Trả về dict kết quả.
    """
    import re

    result = {
        "item_id": item_id,
        "status": "PENDING",
        "audio_dir": None,
        "new_logprob": None,
        "new_quality": None,
        "stages": [],
        "files_replaced": [],
        "error": None,
    }

    base = Path(".")
    base_item_id = get_base_item_id(item_id)

    # 1. Tìm thư mục audio chứa file này
    audio_dir, week_name, date_str = find_original_wav_dir(item_id, base)

    # Dùng hint nếu không tìm thấy
    if not audio_dir and date_hint and week_hint:
        candidate_dir = base / week_hint / date_hint / "audio"
        if candidate_dir.exists():
            audio_dir = candidate_dir
            week_name = week_hint
            date_str = date_hint

    if not audio_dir:
        result["status"] = "SKIP_NOT_FOUND"
        result["error"] = f"Cannot find audio dir for {item_id}"
        return result

    result["audio_dir"] = str(audio_dir)

    # Xác định tất cả file liên quan (có thể có nhiều slice)
    related_wavs = sorted(audio_dir.glob(f"{base_item_id}*.wav"))
    # Nếu chưa có file nào trên đĩa, đích đến là file WAV mới
    if not related_wavs:
        related_wavs = [audio_dir / f"{base_item_id}.wav"]

    target_url = video_url_hint or lookup_original_video_url(audio_dir, item_id)
    if not target_url:
        target_url = build_tiktok_url(item_id)

    # 3. Download MP4 video + extract WAV
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        mp4_path = tmp / f"{base_item_id}.mp4"

        # Ưu tiên TikWM cho TikTok
        is_tiktok = not base_item_id.startswith("fb_")
        if is_tiktok:
            try:
                tikwm = TikWMClient()
                time.sleep(0.5)
                video_info = tikwm.get_video_info(target_url)
                if video_info and video_info.get("play_url"):
                    tikwm.download_video(video_info["play_url"], mp4_path)
            except Exception as e:
                logger.debug(f"[TikWM] notice: {e}")

        # Fallback qua yt-dlp nếu TikWM không tải được hoặc là Facebook
        if not mp4_path.exists() or mp4_path.stat().st_size < 10_000:
            try:
                import yt_dlp
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "outtmpl": str(tmp / f"{base_item_id}.%(ext)s"),
                    "format": "bestvideo+bestaudio/best[ext=mp4]/best",
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([target_url])
                # Tìm file MP4 hoặc video đã download
                dl_files = list(tmp.glob(f"{base_item_id}.*"))
                if dl_files:
                    mp4_path = dl_files[0]
            except Exception as ydl_exc:
                result["status"] = "DOWNLOAD_FAILED"
                result["error"] = f"yt-dlp fallback failed: {ydl_exc}"
                return result

        if not mp4_path.exists() or mp4_path.stat().st_size < 10_000:
            result["status"] = "DOWNLOAD_FAILED"
            result["error"] = "Both TikWM and yt-dlp failed to download"
            return result

        raw_wav = tmp / f"{base_item_id}_raw.wav"
        ffmpeg_res = subprocess.run([
            "ffmpeg", "-y", "-i", str(mp4_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(raw_wav)
        ], capture_output=True, timeout=60)

        if ffmpeg_res.returncode != 0 or not raw_wav.exists():
            result["status"] = "EXTRACT_FAILED"
            result["error"] = f"FFmpeg extract failed: {ffmpeg_res.stderr[-200:]}"
            return result

        # 4. SpeechMaster 4 tầng
        master = get_speech_master()
        sm_result = master.process(raw_wav, overwrite=True)

        result["stages"] = sm_result.get("stages_applied", [])
        result["new_logprob"] = sm_result.get("avg_logprob")
        result["new_quality"] = sm_result.get("raw_quality")

        if not sm_result.get("pass", False):
            reason = sm_result.get("reason", "unknown")
            result["status"] = f"SPEECH_MASTER_REJECT:{reason}"
            result["error"] = reason
            return result

        # 5. Ghi đè file WAV cũ
        # Nếu có nhiều slice (tt_VIDEOID_01.wav, tt_VIDEOID_02.wav...) → thay toàn bộ bằng file đơn
        if not dry_run:
            if len(related_wavs) == 1:
                # 1 file: ghi đè trực tiếp
                dest = related_wavs[0]
                shutil.copy2(str(raw_wav), str(dest))
                result["files_replaced"] = [str(dest)]
            else:
                # Nhiều slice: xóa tất cả, lưu file gốc với tên base
                dest = audio_dir / f"{base_item_id}.wav"
                for old_wav in related_wavs:
                    old_wav.unlink(missing_ok=True)
                shutil.copy2(str(raw_wav), str(dest))
                result["files_replaced"] = [str(w) for w in related_wavs]

            # Cập nhật metadata.json
            new_dur = max(0.0, (dest.stat().st_size - 44) / 32000.0)
            update_date_metadata(audio_dir, base_item_id, new_dur, {
                "raw_quality": result["new_quality"],
                "avg_logprob": result["new_logprob"],
                "stages": result["stages"],
            })

            lp_str = f"{result['new_logprob']:.3f}" if result['new_logprob'] is not None else "?"
            result["status"] = "SUCCESS"
            logger.info(
                f"[RecrawlOK] {item_id} | quality={result['new_quality']} "
                f"lp={lp_str} | {week_name}/{date_str} "
                f"| replaced {len(result['files_replaced'])} file(s)"
            )
        else:
            lp_str = f"{result['new_logprob']:.3f}" if result['new_logprob'] is not None else "?"
            result["status"] = "DRY_RUN_OK"
            result["files_replaced"] = [str(w) for w in related_wavs]
            logger.info(
                f"[DryRun] {item_id} would replace {len(related_wavs)} file(s) "
                f"(lp={lp_str})"
            )

    return result


def load_bad_file_list(report_path: str | None, ids_file: str | None, manifest_path: str | None = None) -> list[dict]:
    """Đọc danh sách file lỗi từ manifest JSON, report JSON hoặc .txt file."""
    entries = []

    if manifest_path:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        for t in data.get("targets", []):
            entries.append({
                "item_id": t["item_id"],
                "video_url": t.get("video_url"),
                "date": t.get("date"),
                "week": t.get("week"),
                "relative_path": t.get("relative_path"),
                "absolute_path": t.get("absolute_path"),
                "old_status": t.get("error_type"),
            })
    elif report_path:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        for bf in report.get("bad_files", []):
            if bf.get("status") in ("EMPTY_TRANSCRIPT", "NO_SPEECH", "LOW_QUALITY",
                                    "DUPLICATE_HASH", "CORRUPT") or "error_type" in bf:
                entries.append({
                    "item_id": bf["item_id"],
                    "video_url": bf.get("video_url"),
                    "date": bf.get("date"),
                    "week": bf.get("week"),
                    "old_status": bf.get("status") or bf.get("error_type"),
                })
    elif ids_file:
        lines = Path(ids_file).read_text(encoding="utf-8").splitlines()
        for line in lines:
            item_id = line.strip()
            if item_id:
                entries.append({"item_id": item_id, "video_url": None, "date": None, "week": None, "old_status": "unknown"})

    return entries


def main():
    parser = argparse.ArgumentParser(description="Cào lại file audio lỗi bằng TikWM Engine")
    parser.add_argument("--manifest", type=str, default=None,
                        help="File recrawl_manifest.json từ master_full_audit.py")
    parser.add_argument("--report", type=str, default=None,
                        help="File JSON từ detect_bad_files.py")
    parser.add_argument("--ids", type=str, default=None,
                        help="File .txt chứa danh sách item_ids (tt_XXXX), mỗi dòng 1 ID")
    parser.add_argument("--date", type=str, default=None,
                        help="Chỉ cào lại các file của ngày cụ thể (VD: 2026-08-24)")
    parser.add_argument("--use-demucs", action="store_true", default=False,
                        help="Kích hoạt Meta Demucs v4 (mặc định False để dùng DSP siêu tốc trên CPU)")
    parser.add_argument("--workers", type=int, default=2,
                        help="Số luồng download song song (khuyến nghị 2-4)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Giới hạn số file cào lại (để test)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chỉ test, không ghi đè file gốc")
    args = parser.parse_args()

    if not args.manifest and not args.report and not args.ids:
        print("Cần chỉ định --manifest <recrawl_manifest.json>, --report <file.json> hoặc --ids <file.txt>")
        parser.print_help()
        sys.exit(1)

    print(f"\n{'='*65}")
    print("  RECRAWL BAD FILES — TikWM Engine + SpeechMaster 4 Tang")
    print(f"{'='*65}")
    print(f"  Dry Run    : {args.dry_run}")
    print(f"  Workers    : {args.workers}")
    print(f"  Demucs     : {args.use_demucs}")
    if args.date:
        print(f"  Date Filter: {args.date}")

    # Load Whisper model trước (để không bị race condition khi dùng thread pool)
    print("\n[*] Pre-loading SpeechMaster + Whisper model...")
    get_speech_master(use_demucs=args.use_demucs)
    print("[+] Model ready\n")

    entries = load_bad_file_list(args.report, args.ids, manifest_path=args.manifest)
    if args.date:
        entries = [e for e in entries if e.get("date") == args.date]
        print(f"[*] Đã lọc danh sách theo ngày {args.date}: {len(entries)} files")

    completed_checkpoint = load_checkpoint()
    total_requested = len(entries)
    entries = [e for e in entries if e["item_id"] not in completed_checkpoint]
    print(f"[*] Tổng mục tiêu: {total_requested:,} | Đã xong từ trước: {len(completed_checkpoint):,} | Cần cào tiếp: {len(entries):,}\n")

    if args.limit:
        entries = entries[: args.limit]

    results = []
    t0 = time.time()

    if args.workers <= 1:
        # Sequential (an toàn hơn cho CPU-bound Whisper)
        for i, entry in enumerate(entries, 1):
            print(f"[{i}/{len(entries)}] {entry['item_id']} ({entry.get('old_status', '?')})", flush=True)
            r = recrawl_one(
                entry["item_id"],
                entry.get("date"),
                entry.get("week"),
                video_url_hint=entry.get("video_url"),
                dry_run=args.dry_run,
            )
            r["old_status"] = entry.get("old_status")
            results.append(r)
            completed_checkpoint.add(entry["item_id"])
            if len(completed_checkpoint) % 5 == 0:
                save_checkpoint(completed_checkpoint, {"total": total_requested, "done": len(completed_checkpoint)})

            if r["status"] in ("SUCCESS", "DRY_RUN_OK"):
                lp = f"{r['new_logprob']:.3f}" if r.get("new_logprob") is not None else "?"
                print(f"  -> {r['status']} | lp={lp} | quality={r['new_quality']}")
            else:
                print(f"  -> {r['status']} | {r.get('error', '')}")
    else:
        # Parallel download (Whisper vẫn single-threaded)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(recrawl_one, e["item_id"], e.get("date"), e.get("week"), e.get("video_url"), args.dry_run): e
                for e in entries
            }
            done = 0
            for future in as_completed(futures):
                done += 1
                entry = futures[future]
                try:
                    r = future.result()
                    r["old_status"] = entry.get("old_status")
                    results.append(r)
                    completed_checkpoint.add(entry["item_id"])
                    if len(completed_checkpoint) % 5 == 0:
                        save_checkpoint(completed_checkpoint, {"total": total_requested, "done": len(completed_checkpoint)})
                    if done % 10 == 0 or r["status"] == "SUCCESS":
                        ok_count = sum(1 for x in results if x["status"] in ("SUCCESS", "DRY_RUN_OK"))
                        print(f"  [{done}/{len(entries)}] {r['item_id']} -> {r['status']} | OK so far: {ok_count}")
                except Exception as exc:
                    results.append({"item_id": entry["item_id"], "status": f"EXCEPTION:{exc}", "old_status": entry.get("old_status")})

    elapsed = time.time() - t0

    # ── Thống kê kết quả ────────────────────────────────────────────────
    total = len(results)
    success = sum(1 for r in results if r["status"] in ("SUCCESS", "DRY_RUN_OK"))
    failed = total - success

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    print(f"\n{'='*65}")
    print(f"  KET QUA RECRAWL ({elapsed:.0f}s | {elapsed/max(total,1):.1f}s/file avg)")
    print(f"{'='*65}")
    print(f"  Tong file      : {total:,}")
    print(f"  Thanh cong     : {success:,} ({success/max(total,1)*100:.1f}%)")
    print(f"  That bai       : {failed:,} ({failed/max(total,1)*100:.1f}%)")
    print()
    for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {status:35s}: {count:,}")

    # Lưu kết quả
    now_str = datetime.now(VN_TZ).strftime("%Y%m%d_%H%M%S")
    result_path = RESULT_DIR / f"recrawl_result_{now_str}.json"
    result_path.write_text(json.dumps({
        "generated_at": datetime.now(VN_TZ).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "total": total,
        "success": success,
        "failed": failed,
        "by_status": by_status,
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[+] Ket qua da luu: {result_path}")


if __name__ == "__main__":
    main()
