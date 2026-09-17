#!/usr/bin/env bash
set -e

echo "=== KHỞI CHẠY PIPELINE NHÁNH MELBAND-ROFORMER (STUDIO SOTA QUALITY) ==="
URLS_FILE=${1:-"urls.txt"}
OUTPUT_DIR=${2:-"data/melband_gold_dataset"}

python src/pipeline.py \
  --urls "$URLS_FILE" \
  --output "$OUTPUT_DIR" \
  --model melband \
  --device cuda
