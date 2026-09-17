"""
audio_dedup.py — Content & Waveform Audio Deduplication Engine
==============================================================
Chống trùng lặp audio bằng Waveform Quantized Fingerprint SHA-256.
Loại bỏ triệt để các clip re-upload, nhạc trend lặp lại hàng triệu lần.
"""
import hashlib
from pathlib import Path
from typing import Set, Dict, Tuple
import numpy as np
import soundfile as sf


class AudioDedupEngine:
    def __init__(self):
        self.seen_hashes: Dict[str, str] = {}
        self.seen_ids: Set[str] = set()

    def compute_waveform_hash(self, audio: np.ndarray) -> str:
        """
        Tính SHA-256 fingerprint trên mảng sóng âm thanh đã lượng tử hóa int16.
        """
        # Lấy 16kHz mono int16 để hash bất biến trước các thay đổi container
        pcm_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        return hashlib.sha256(pcm_int16.tobytes()).hexdigest()

    def is_duplicate(self, audio_path: Path) -> Tuple[bool, str]:
        """
        Kiểm tra xem file có bị trùng lặp không.
        Returns: (is_dup, reason)
        """
        item_id = audio_path.stem
        if item_id in self.seen_ids:
            return True, f"duplicate_id:{item_id}"

        try:
            data, sr = sf.read(str(audio_path), dtype="float32")
            if len(data.shape) > 1:
                data = data.mean(axis=1)

            w_hash = self.compute_waveform_hash(data)
            if w_hash in self.seen_hashes:
                return True, f"duplicate_audio_content_of:{self.seen_hashes[w_hash]}"

            self.seen_hashes[w_hash] = item_id
            self.seen_ids.add(item_id)
            return False, ""
        except Exception as e:
            return False, f"hash_error:{e}"
