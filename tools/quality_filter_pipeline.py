#!/usr/bin/env python3
"""
quality_filter_pipeline.py — Speech AI Data Quality Filter Pipeline
====================================================================
Loc audio theo 4 tieu chi nghiem thu:
  1. Dedup (SHA-256 waveform hash): loai bo trung lap ngay tu dau de tiet kiem CPU/GPU
  2. VAD (Silero): loai file khong co tieng nguoi (speech_ratio < 0.3)
  3. Music/BGM check (librosa): loai file nhac lan tieng (spectral flatness)
  4. Format normalize: WAV 16kHz, mono, 16-bit PCM, -20 LUFS target

Output:
  <output>/approved/      -- file dat chuan
  <output>/rejected/      -- file bi loai (kem ly do trong ten thu muc con)
  <output>/metadata.jsonl -- metadata day du moi file

Usage:
  python tools/quality_filter_pipeline.py --input /path/to/audio --output /path/to/output
  python tools/quality_filter_pipeline.py --input ./data --output ./results --workers 4
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf
import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

TARGET_SR = 16_000
TARGET_CHANNELS = 1
TARGET_SUBTYPE = "PCM_16"
MIN_SPEECH_RATIO = 0.30
MAX_SPECTRAL_FLATNESS = 0.15
MAX_MUSIC_RATIO = 0.50
MIN_DURATION_SEC = 1.0
MAX_DURATION_SEC = 30.0
LUFS_TARGET = -20.0

_vad_model = None
_vad_utils = None


def get_vad_model():
    global _vad_model, _vad_utils
    if _vad_model is None:
        log.info("Loading Silero VAD model...")
        _vad_model, _vad_utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )
        _vad_model.eval()
    return _vad_model, _vad_utils


def load_audio_mono_16k(path: Path) -> Tuple[np.ndarray, int]:
    import librosa
    y, sr = librosa.load(str(path), sr=TARGET_SR, mono=True)
    return y, sr


def check_speech_ratio(audio: np.ndarray, sr: int) -> float:
    vad_model, (get_speech_ts, *_) = get_vad_model()
    tensor = torch.from_numpy(audio).float()
    with torch.no_grad():
        speech_timestamps = get_speech_ts(
            tensor, vad_model, sampling_rate=sr,
            threshold=0.5, min_speech_duration_ms=250,
        )
    total_speech_samples = sum(ts["end"] - ts["start"] for ts in speech_timestamps)
    return float(total_speech_samples / max(len(audio), 1))


def check_music_ratio(audio: np.ndarray, sr: int) -> Tuple[float, float]:
    import librosa
    S = np.abs(librosa.stft(audio, n_fft=2048, hop_length=512))
    flatness = librosa.feature.spectral_flatness(S=S)[0]
    mean_flatness = float(np.mean(flatness))
    music_frames = np.sum(flatness > MAX_SPECTRAL_FLATNESS)
    music_ratio = float(music_frames / max(len(flatness), 1))
    return music_ratio, mean_flatness


def compute_audio_hash(audio: np.ndarray) -> str:
    pcm_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    return hashlib.sha256(pcm_int16.tobytes()).hexdigest()


def normalize_and_write(audio: np.ndarray, sr: int, out_path: Path):
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms > 1e-9:
        target_rms = 10 ** (LUFS_TARGET / 20.0)
        audio = audio * (target_rms / rms)
    audio = np.clip(audio, -1.0, 1.0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), audio, samplerate=sr, subtype=TARGET_SUBTYPE)


def _estimate_snr(audio: np.ndarray, sr: int) -> float:
    import librosa
    rms_frames = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
    if len(rms_frames) < 3:
        return 0.0
    rms_frames = np.sort(rms_frames)
    n = max(1, len(rms_frames) // 3)
    signal_rms = float(np.mean(rms_frames[-n:]))
    noise_rms = float(np.mean(rms_frames[:n]))
    if noise_rms < 1e-9:
        return 60.0
    return round(float(20 * np.log10(signal_rms / noise_rms)), 2)


def _copy_to_rejected(src: Path, output_dir: Path, reason: str):
    dst_dir = output_dir / "rejected" / reason
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)


def process_file(
    audio_path: Path,
    output_dir: Path,
    seen_hashes: Dict[str, str],
    source_id: str = "",
) -> dict:
    result = {
        "audio_path": str(audio_path),
        "source_id": source_id or audio_path.stem,
        "label": "research_only",
        "status": "unknown",
        "reject_reason": None,
        "duration": None,
        "speech_ratio": None,
        "music_ratio": None,
        "spectral_flatness": None,
        "snr_score": None,
        "audio_hash": None,
        "output_path": None,
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        audio, sr = load_audio_mono_16k(audio_path)
        duration = len(audio) / sr
        result["duration"] = round(duration, 3)

        if duration < MIN_DURATION_SEC:
            result["status"] = "rejected"
            result["reject_reason"] = "too_short"
            _copy_to_rejected(audio_path, output_dir, "too_short")
            return result

        if duration > MAX_DURATION_SEC:
            result["status"] = "rejected"
            result["reject_reason"] = "too_long"
            _copy_to_rejected(audio_path, output_dir, "too_long")
            return result

        # ── Step 1: Dedup hash check (Tối ưu performance) ───────────────────
        audio_hash = compute_audio_hash(audio)
        result["audio_hash"] = audio_hash
        if audio_hash in seen_hashes:
            result["status"] = "rejected"
            result["reject_reason"] = f"duplicate_of:{seen_hashes[audio_hash]}"
            _copy_to_rejected(audio_path, output_dir, "duplicate")
            return result
        seen_hashes[audio_hash] = str(audio_path)

        # ── Step 2: VAD check ───────────────────────────────────────────────
        speech_ratio = check_speech_ratio(audio, sr)
        result["speech_ratio"] = round(speech_ratio, 4)
        if speech_ratio < MIN_SPEECH_RATIO:
            result["status"] = "rejected"
            result["reject_reason"] = "no_speech"
            _copy_to_rejected(audio_path, output_dir, "no_speech")
            return result

        # ── Step 3: Music/BGM check ─────────────────────────────────────────
        music_ratio, mean_flatness = check_music_ratio(audio, sr)
        result["music_ratio"] = round(music_ratio, 4)
        result["spectral_flatness"] = round(mean_flatness, 6)
        if music_ratio > MAX_MUSIC_RATIO:
            result["status"] = "rejected"
            result["reject_reason"] = "music_dominant"
            _copy_to_rejected(audio_path, output_dir, "music_dominant")
            return result

        result["snr_score"] = _estimate_snr(audio, sr)

        # ── Step 4: Normalize & write approved file ─────────────────────────
        approved_dir = output_dir / "approved"
        out_path = approved_dir / audio_path.name
        normalize_and_write(audio, sr, out_path)
        result["status"] = "approved"
        result["output_path"] = str(out_path)

    except Exception as e:
        log.warning(f"Error processing {audio_path}: {e}")
        result["status"] = "error"
        result["reject_reason"] = str(e)

    return result


def run_pipeline(input_dir: Path, output_dir: Path, workers: int, extensions: List[str]):
    audio_files = []
    for ext in extensions:
        audio_files.extend(sorted(input_dir.rglob(f"*.{ext}")))

    if not audio_files:
        log.error(f"No audio files found in {input_dir}")
        sys.exit(1)

    log.info(f"Found {len(audio_files)} audio files. Starting pipeline with {workers} workers...")
    output_dir.mkdir(parents=True, exist_ok=True)

    seen_hashes: Dict[str, str] = {}
    metadata_records = []
    stats: Dict[str, int] = {"approved": 0, "rejected": 0, "error": 0}
    reject_reasons: Dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_file, f, output_dir, seen_hashes, f.stem): f for f in audio_files}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                rec = future.result()
            except Exception as e:
                rec = {"status": "error", "reject_reason": str(e)}
            metadata_records.append(rec)
            status = rec.get("status", "error")
            stats[status] = stats.get(status, 0) + 1
            reason = rec.get("reject_reason") or ""
            if reason:
                base_reason = reason.split(":")[0]
                reject_reasons[base_reason] = reject_reasons.get(base_reason, 0) + 1
            if i % 50 == 0 or i == len(audio_files):
                log.info(
                    f"Progress: {i}/{len(audio_files)} | "
                    f"Approved: {stats['approved']} | "
                    f"Rejected: {stats.get('rejected', 0)} | "
                    f"Errors: {stats.get('error', 0)}"
                )

    meta_path = output_dir / "metadata.jsonl"
    with open(meta_path, "w", encoding="utf-8") as f:
        for rec in metadata_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total = len(audio_files)
    approved = stats.get("approved", 0)
    rejected = stats.get("rejected", 0)
    errors = stats.get("error", 0)
    dup_count = reject_reasons.get("duplicate", 0)
    dup_rate = dup_count / max(total, 1) * 100

    log.info("\n" + "=" * 60)
    log.info("DATA FUNNEL REPORT")
    log.info("=" * 60)
    log.info(f"  Raw input        : {total:>6,} files  (100%)")
    no_speech = reject_reasons.get("no_speech", 0)
    music_dom = reject_reasons.get("music_dominant", 0)
    log.info(f"  After VAD        : {total - no_speech:>6,} files  ({(total-no_speech)/max(total,1)*100:.1f}%)")
    log.info(f"  After BGM filter : {total - no_speech - music_dom:>6,} files  ({(total-no_speech-music_dom)/max(total,1)*100:.1f}%)")
    log.info(f"  Final approved   : {approved:>6,} files  ({approved/max(total,1)*100:.1f}%)")
    log.info(f"  Total rejected   : {rejected:>6,} files  ({rejected/max(total,1)*100:.1f}%)")
    log.info(f"  Errors           : {errors:>6,}")
    log.info(f"  Duplication rate : {dup_rate:.2f}% (limit: 5%)")
    log.info(f"\n  Reject breakdown:")
    for reason, count in sorted(reject_reasons.items(), key=lambda x: -x[1]):
        log.info(f"    {reason:<22}: {count:>5,} ({count/max(total,1)*100:.1f}%)")
    log.info("=" * 60)
    log.info(f"Outputs: {output_dir}/approved/  |  {output_dir}/rejected/  |  metadata.jsonl")
    return stats


def parse_args():
    parser = argparse.ArgumentParser(description="Speech AI Data Quality Filter Pipeline")
    parser.add_argument("--input", "-i", required=True, type=Path, help="Thu muc chua file audio")
    parser.add_argument("--output", "-o", required=True, type=Path, help="Thu muc output")
    parser.add_argument("--workers", "-w", type=int, default=4, help="So luong workers (default: 4)")
    parser.add_argument("--ext", nargs="+", default=["wav", "mp3", "flac", "m4a"], help="Dinh dang file")
    parser.add_argument("--speech-ratio", type=float, default=MIN_SPEECH_RATIO)
    parser.add_argument("--music-ratio", type=float, default=MAX_MUSIC_RATIO)
    return parser.parse_args()


def main():
    args = parse_args()
    global MIN_SPEECH_RATIO, MAX_MUSIC_RATIO
    MIN_SPEECH_RATIO = args.speech_ratio
    MAX_MUSIC_RATIO = args.music_ratio
    if not args.input.exists():
        log.error(f"Input directory not found: {args.input}")
        sys.exit(1)
    log.info(f"Quality Filter Pipeline | Input: {args.input} | Output: {args.output} | Workers: {args.workers}")
    run_pipeline(args.input, args.output, args.workers, args.ext)


if __name__ == "__main__":
    main()
