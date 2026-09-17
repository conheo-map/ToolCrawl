#!/usr/bin/env bash
set -e

echo "=== KHỞI CHẠY PIPELINE NHÁNH DEMUCS (FAST HIGH-THROUGHPUT) ==="
URLS_FILE=${1:-"urls.txt"}
OUTPUT_DIR=${2:-"data/demucs_gold_dataset"}

python src/pipeline.py \
  --urls "$URLS_FILE" \
  --output "$OUTPUT_DIR" \
  --model demucs \
  --device cuda
