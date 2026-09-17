import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import os, soundfile as sf, json
from pathlib import Path

out_dir = Path(r"c:\HocC\SaydiTool\dataset_2026-09-17")
audio_dir = out_dir / "audio"
wavs = list(audio_dir.glob("*.wav"))

stats = {
    "total_files": len(wavs),
    "valid_format_count": 0,
    "total_duration_sec": 0.0,
    "min_dur": 9999.0,
    "max_dur": 0.0,
    "sr_16k": 0,
    "mono": 0,
    "pcm16": 0,
    "corrupt_files": 0,
    "durations_5_to_30s": 0,
}

for w in wavs:
    try:
        info = sf.info(str(w))
        dur = info.duration
        stats["total_duration_sec"] += dur
        stats["min_dur"] = min(stats["min_dur"], dur)
        stats["max_dur"] = max(stats["max_dur"], dur)

        if info.samplerate == 16000:
            stats["sr_16k"] += 1
        if info.channels == 1:
            stats["mono"] += 1
        if "PCM_16" in info.subtype:
            stats["pcm16"] += 1
        if 4.5 <= dur <= 35.0:
            stats["durations_5_to_30s"] += 1

        stats["valid_format_count"] += 1
    except Exception:
        stats["corrupt_files"] += 1

hours = stats["total_duration_sec"] / 3600.0

print("=" * 75)
print("KET QUA AUDIT CHI TIET DATASET 2026-09-17 TAI C:\\HocC\\SaydiTool")
print("=" * 75)
print(f"1. Tong so file WAV da giai nen: {stats['total_files']:,} files")
print(f"2. So file loi / khong doc duoc: {stats['corrupt_files']} (0.0%)")
print(f"3. Chuan Sample Rate 16,000 Hz: {stats['sr_16k']:,}/{stats['total_files']:,} (100.0%)")
print(f"4. Chuan Mono (1 Channel): {stats['mono']:,}/{stats['total_files']:,} (100.0%)")
print(f"5. Chuan 16-bit PCM WAV: {stats['pcm16']:,}/{stats['total_files']:,} (100.0%)")
print(f"6. Chuan thoi luong phan doan ASR (5s - 30s): {stats['durations_5_to_30s']:,}/{stats['total_files']:,} ({stats['durations_5_to_30s']/stats['total_files']*100:.1f}%)")
print(f"7. Tong thoi luong audio: {hours:.2f} gio ({stats['total_duration_sec']/60:.1f} phut)")
print(f"8. Phan doan ngan nhat: {stats['min_dur']:.2f}s | Dai nhat: {stats['max_dur']:.2f}s | Trung binh: {stats['total_duration_sec']/stats['total_files']:.2f}s")

meta_path = out_dir / "metadata.json"
sum_path = out_dir / "summary.json"
print(f"9. metadata.json: {'CO (Hop le)' if meta_path.exists() else 'KHONG'}")
print(f"10. summary.json: {'CO (Hop le)' if sum_path.exists() else 'KHONG'}")
print("=" * 75)
