"""
silero_slicer.py — Silero VAD Speech Segmentation Engine
========================================================
Cắt audio thành các đoạn câu nói tự nhiên (3s - 15s) dựa trên Voice Activity Detection.
Loại bỏ 100% khoảng lặng vô nghĩa và các đoạn intro/outro nhạc không có tiếng người.
"""
from pathlib import Path
from typing import List, Dict
import torch
import soundfile as sf
import numpy as np


class SileroVADSlicer:
    def __init__(
        self,
        min_segment_sec: float = 3.0,
        max_segment_sec: float = 15.0,
        threshold: float = 0.5,
        min_speech_ms: int = 250,
        min_silence_ms: int = 300,
        pre_padding_sec: float = 0.2,
        post_padding_sec: float = 0.2
    ):
        self.min_sec = min_segment_sec
        self.max_sec = max_segment_sec
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self.pre_pad = pre_padding_sec
        self.post_pad = post_padding_sec
        self._load_model()

    def _load_model(self):
        self.model, self.utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True
        )
        self.get_speech_ts = self.utils[0]
        self.model.eval()

    def slice_file(self, audio_path: Path, output_dir: Path) -> List[Dict]:
        """
        Cắt file audio thành các segments ASR đạt chuẩn và lưu vào output_dir.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        data, sr = sf.read(str(audio_path), dtype="float32")
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        total_dur = len(data) / sr
        tensor = torch.from_numpy(data).float()

        with torch.no_grad():
            speech_ts = self.get_speech_ts(
                tensor,
                self.model,
                sampling_rate=sr,
                threshold=self.threshold,
                min_speech_duration_ms=self.min_speech_ms,
                min_silence_duration_ms=self.min_silence_ms
            )

        if not speech_ts:
            return []

        # Ghép các speech timestamp liền kề thành segment từ min_sec đến max_sec
        segments = []
        cur_start = None
        cur_end = None

        for ts in speech_ts:
            st = ts["start"] / sr
            en = ts["end"] / sr

            if cur_start is None:
                cur_start = st
                cur_end = en
                continue

            # Nếu ghép thêm vẫn <= max_sec thì gộp
            if (en - cur_start) <= self.max_sec:
                cur_end = en
            else:
                # Lưu đoạn hiện tại nếu đủ min_sec
                if (cur_end - cur_start) >= self.min_sec:
                    segments.append((cur_start, cur_end))
                cur_start = st
                cur_end = en

        if cur_start is not None and (cur_end - cur_start) >= self.min_sec:
            segments.append((cur_start, cur_end))

        # Xuất các file wav segment
        results = []
        base_name = audio_path.stem
        for idx, (st, en) in enumerate(segments, start=1):
            st_pad = max(0.0, st - self.pre_pad)
            en_pad = min(total_dur, en + self.post_pad)
            dur = round(en_pad - st_pad, 3)

            seg_data = data[int(st_pad * sr): int(en_pad * sr)]
            if len(seg_data) == 0:
                continue

            seg_filename = f"{base_name}_{idx:02d}.wav" if len(segments) > 1 else f"{base_name}.wav"
            seg_path = output_dir / seg_filename

            # Chuẩn hóa loudness (-20 LUFS approx)
            rms = float(np.sqrt(np.mean(seg_data ** 2)))
            if rms > 1e-9:
                target_rms = 10 ** (-20.0 / 20.0)
                seg_data = seg_data * (target_rms / rms)
            seg_data = np.clip(seg_data, -1.0, 1.0)

            sf.write(str(seg_path), seg_data, sr, subtype="PCM_16")

            results.append({
                "segment_id": seg_path.stem,
                "audio_path": str(seg_path),
                "duration_seconds": dur,
                "start_time": round(st_pad, 3),
                "end_time": round(en_pad, 3)
            })

        return results
