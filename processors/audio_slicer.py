"""
processors/audio_slicer.py — Bộ cắt audio thông minh theo khoảng lặng tự nhiên (Smart ASR Slicer).
Chia các audio dài thành các phân đoạn 5s - 30s đạt chuẩn huấn luyện ASR quốc tế.
"""

import re
import subprocess
import shutil
from pathlib import Path
from utils.logger import get_logger
from config import (
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    AUDIO_CODEC,
)

logger = get_logger("audio_slicer")

MAX_ASR_SEGMENT_SEC: float = 30.0
MIN_ASR_SEGMENT_SEC: float = 5.0
SILENCE_THRESHOLD_DB: float = -32.0
MIN_SILENCE_DURATION_SEC: float = 0.35


class AudioSlicer:
    """
    Phát hiện khoảng lặng (silence) và cắt audio thành các phân đoạn 5s - 30s.
    Không cắt ngang câu nói của người nói.
    """

    def __init__(
        self,
        max_segment_sec: float = MAX_ASR_SEGMENT_SEC,
        min_segment_sec: float = MIN_ASR_SEGMENT_SEC,
        silence_thresh_db: float = SILENCE_THRESHOLD_DB,
        min_silence_dur: float = MIN_SILENCE_DURATION_SEC,
    ) -> None:
        self.max_sec = max_segment_sec
        self.min_sec = min_segment_sec
        self.silence_thresh = silence_thresh_db
        self.min_silence = min_silence_dur

    def detect_silences(self, audio_path: Path) -> list[dict]:
        """
        Dùng FFmpeg silencedetect để lấy danh sách các điểm lặng trong audio.
        Trả về list of dict: [{'start': float, 'end': float, 'mid': float}]
        """
        if not shutil.which("ffmpeg"):
            return []

        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-af", f"silencedetect=noise={self.silence_thresh}dB:d={self.min_silence}",
            "-f", "null",
            "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        stderr = res.stderr

        silence_starts = []
        silence_ends = []

        for line in stderr.splitlines():
            m_start = re.search(r"silence_start:\s*([0-9.]+)", line)
            if m_start:
                silence_starts.append(float(m_start.group(1)))
            m_end = re.search(r"silence_end:\s*([0-9.]+)", line)
            if m_end:
                silence_ends.append(float(m_end.group(1)))

        silences = []
        for i in range(min(len(silence_starts), len(silence_ends))):
            st = silence_starts[i]
            en = silence_ends[i]
            if en > st:
                silences.append({
                    "start": st,
                    "end": en,
                    "mid": round((st + en) / 2.0, 3),
                })
        return silences

    def calculate_split_points(self, total_duration: float, silences: list[dict]) -> list[tuple[float, float]]:
        """
        Tính toán danh sách (start_sec, end_sec) cho từng đoạn cắt tối ưu trong [min_sec, max_sec].
        """
        if total_duration <= self.max_sec:
            if total_duration >= self.min_sec:
                return [(0.0, total_duration)]
            return []

        mid_points = [s["mid"] for s in silences]
        segments = []
        cur_start = 0.0

        while cur_start < total_duration:
            rem = total_duration - cur_start
            if rem <= self.max_sec:
                if rem >= self.min_sec:
                    segments.append((round(cur_start, 3), round(total_duration, 3)))
                break

            window_min = cur_start + self.min_sec
            window_max = cur_start + self.max_sec

            candidates = [p for p in mid_points if window_min <= p <= window_max]

            if candidates:
                best_cut = candidates[-1]
            else:
                best_cut = window_max

            segments.append((round(cur_start, 3), round(best_cut, 3)))
            cur_start = best_cut

        return segments

    def slice_audio(self, audio_path: Path, item_id: str, output_dir: Path) -> list[dict]:
        """
        Cắt audio thành các file .wav theo chuẩn ASR.
        Nếu file ngắn (<= max_sec), trả về nguyên vẹn 1 phân đoạn.
        """
        from processors.audio_converter import verify_audio

        try:
            info = verify_audio(audio_path)
            total_duration = info["duration_seconds"]
        except Exception as exc:
            logger.warning(f"Cannot verify audio {audio_path.name}: {exc}")
            return []

        if total_duration <= self.max_sec:
            if total_duration >= self.min_sec:
                return [{
                    "item_id": item_id,
                    "audio_path": audio_path,
                    "duration_seconds": total_duration,
                    "segment_index": 1,
                    "total_segments": 1,
                }]
            return []

        silences = self.detect_silences(audio_path)
        splits = self.calculate_split_points(total_duration, silences)

        if not splits:
            return []

        if len(splits) == 1:
            return [{
                "item_id": item_id,
                "audio_path": audio_path,
                "duration_seconds": total_duration,
                "segment_index": 1,
                "total_segments": 1,
            }]

        results = []
        output_dir.mkdir(parents=True, exist_ok=True)

        for idx, (st, en) in enumerate(splits, start=1):
            dur = round(en - st, 3)
            if dur < self.min_sec:
                continue

            seg_item_id = f"{item_id}_{idx:02d}"
            seg_path = output_dir / f"{seg_item_id}.wav"

            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(st),
                "-to", str(en),
                "-i", str(audio_path),
                "-acodec", AUDIO_CODEC,
                "-ar", str(AUDIO_SAMPLE_RATE),
                "-ac", str(AUDIO_CHANNELS),
                "-f", "wav",
                str(seg_path),
            ]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0 and seg_path.exists():
                results.append({
                    "item_id": seg_item_id,
                    "audio_path": seg_path,
                    "duration_seconds": dur,
                    "segment_index": idx,
                    "total_segments": len(splits),
                    "start_sec": st,
                    "end_sec": en,
                })

        logger.info(f"✂️ Sliced {audio_path.name} ({total_duration:.1f}s) -> {len(results)} ASR segments (5s - 30s)")

        if results and audio_path.exists():
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

        return results
