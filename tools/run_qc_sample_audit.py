"""
tools/run_qc_sample_audit.py — Chạy thẩm định thực tế trên các mẫu đại diện của kho dữ liệu.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import json
from pathlib import Path
from tools.qc_asr_specialist_evaluator import analyze_audio_pillars

BASE_DIR = Path(".")
MANIFEST_FILE = BASE_DIR / "tools" / "asr_training_corpus" / "data_manifest_asr_train.jsonl"

manifest_map = {}
if MANIFEST_FILE.exists():
    for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                obj = json.loads(line)
                stem = Path(obj["audio_filepath"]).stem
                manifest_map[stem] = obj.get("text", "")
            except Exception:
                pass

samples = []
for mf in BASE_DIR.glob("Week*/*/metadata.json"):
    recs = json.loads(mf.read_text(encoding="utf-8"))
    for r in recs:
        iid = r["item_id"]
        wav_p = mf.parent / "audio" / f"{iid}.wav"
        if wav_p.exists():
            text = manifest_map.get(iid, "")
            # Lấy đa dạng mẫu
            title_lower = (r.get("title", "") + " " + text).lower()
            samples.append((wav_p, text, r))
            if len(samples) >= 500: # Lấy 500 mẫu
                break
    if len(samples) >= 500:
        break

print(f"[*] Đang thẩm định khắt khe {len(samples)} mẫu âm thanh theo 5 trụ cột ASR...")

decisions = {"KEEP": 0, "RECRAWL": 0, "DELETE": 0}
decision_samples = {"KEEP": [], "RECRAWL": [], "DELETE": []}

for wav_p, text, meta in samples:
    score, dec, p_scores, det, reasons = analyze_audio_pillars(wav_p, text, meta)
    decisions[dec] += 1
    if len(decision_samples[dec]) < 3:
        decision_samples[dec].append({
            "item_id": meta["item_id"],
            "score": score,
            "decision": dec,
            "duration": det.get("duration"),
            "pillar_scores": p_scores,
            "reasons": reasons,
            "title": meta.get("title", "")[:60],
            "text": text[:80]
        })

print("\n" + "=" * 85)
print("  KẾT QUẢ THẨM ĐỊNH THỰC TẾ TRÊN 500 MẪU ĐẠI DIỆN")
print("=" * 85)
for dec, count in decisions.items():
    print(f"  - {dec:8s}: {count:3d} mẫu ({count/len(samples)*100:.1f}%)")

print("\n" + "-" * 85)
print("  CHI TIẾT MẪU ĐIỂN HÌNH TỪNG NHÓM QUYẾT ĐỊNH:")
print("-" * 85)

for dec, items in decision_samples.items():
    print(f"\n>>> NHÓM: {dec} <<<")
    for it in items:
        print(f"  * [{it['item_id']}] Điểm: {it['score']}/10.0 | Độ dài: {it['duration']}s")
        print(f"    - Điểm trụ cột: {it['pillar_scores']}")
        print(f"    - Lý do: {', '.join(it['reasons'])}")
        print(f"    - Tiêu đề: {it['title']}")
        print(f"    - Transcript: {it['text']}...\n")
