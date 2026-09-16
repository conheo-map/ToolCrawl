"""
tools/export_whisper_dataset.py — Đóng gói tập dữ liệu Train/Val/Test cho Whisper Fine-tuning.

[SPRINT 3 — GIAI ĐOẠN 3.1]
Quét toàn bộ metadata từ Week1 đến Week4:
  1. Chỉ lấy các file WAV thực tế tồn tại và có transcript hợp lệ (>= 3 từ).
  2. Phân chia Train (85%), Val (10%), Test Clean (5%).
  3. Xuất file manifest dạng JSONL chuẩn định dạng Hugging Face Datasets / Whisper.
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import random
from pathlib import Path


def export_splits(weeks_root: Path, output_dir: Path, train_ratio=0.85, val_ratio=0.10, seed=42):
    random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_files = list(weeks_root.glob("Week*/*/metadata.json"))
    print(f"[*] Tìm thấy {len(metadata_files)} file metadata.json")

    valid_samples = []

    for meta_path in metadata_files:
        day_dir = meta_path.parent
        audio_dir = day_dir / "audio"
        try:
            records = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            continue

        # Đọc transcripts nếu có ở local_research
        date_str = day_dir.name
        trans_dir = Path("local_research") / date_str / "transcripts"

        for r in records:
            item_id = r.get("item_id")
            wav_path = audio_dir / f"{item_id}.wav"
            if not wav_path.exists():
                continue

            # Tìm text
            text = r.get("title", "")
            if trans_dir.exists():
                t_file = trans_dir / f"{item_id}.txt"
                if t_file.exists():
                    t_content = t_file.read_text(encoding="utf-8").strip()
                    if len(t_content.split()) >= 3:
                        text = t_content

            if len(text.split()) < 3:
                continue

            valid_samples.append({
                "audio_path": str(wav_path.resolve()),
                "relative_path": f"{day_dir.parent.name}/{day_dir.name}/audio/{wav_path.name}",
                "text": text,
                "duration": r.get("duration_seconds", 0.0),
                "music_prob": r.get("music_prob", 0.0),
                "language": "vi",
            })

    print(f"[✓] Tổng số mẫu đạt tiêu chuẩn ASR: {len(valid_samples)}")

    random.shuffle(valid_samples)
    n_total = len(valid_samples)
    n_train = int(n_total * train_ratio)
    n_val = int(n_total * val_ratio)

    train_data = valid_samples[:n_train]
    val_data = valid_samples[n_train:n_train + n_val]
    test_data = valid_samples[n_train + n_val:]

    def write_jsonl(data, file_path: Path):
        with file_path.open("w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    write_jsonl(train_data, output_dir / "train_manifest.jsonl")
    write_jsonl(val_data, output_dir / "val_manifest.jsonl")
    write_jsonl(test_data, output_dir / "test_manifest.jsonl")

    summary = {
        "total_samples": n_total,
        "train_samples": len(train_data),
        "val_samples": len(val_data),
        "test_samples": len(test_data),
        "total_hours": round(sum(x["duration"] for x in valid_samples) / 3600.0, 2),
    }
    (output_dir / "dataset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[✓] Đã xuất Train ({len(train_data)}), Val ({len(val_data)}), Test ({len(test_data)})")
    print(f"[✓] Tổng thời lượng: {summary['total_hours']} giờ")
    print(f"[✓] Thư mục xuất: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Export Whisper Training Manifests")
    parser.add_argument("--weeks-root", type=str, default=".", help="Root folder containing Week1-Week4")
    parser.add_argument("--output-dir", type=str, default="asr_export/manifests", help="Output directory")
    args = parser.parse_args()

    export_splits(Path(args.weeks_root), Path(args.output_dir))


if __name__ == "__main__":
    main()
