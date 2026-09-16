"""
processors/vad_slicer.py — Smart Audio Slicer dung Silero VAD.

[UPGRADE 2.3] Thay the ffmpeg silencedetect bang Silero VAD de phan biet
chinh xac khoang lang giua cau noi vs khoang lang trong nhac nen.

Silero VAD (2MB, real-time CPU) phat hien speech/non-speech theo frame 30ms,
khong bi danh lua boi nhac nen co energy cao.

Interface: Tuong thich hoan toan voi AudioSlicer.slice_audio()
Fallback:  Neu silero-vad chua cai -> dung AudioSlicer goc
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from utils.logger import get_logger
from config import (
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    AUDIO_CODEC,
    MAX_ASR_SEGMENT_SEC,
    MIN_ASR_SEGMENT_SEC,
    PRE_SPEECH_PADDING_SEC,
    POST_SPEECH_PADDING_SEC,
    SILERO_VAD_THRESHOLD,
    SILERO_MIN_SPEECH_MS,
    SILERO_MIN_SILENCE_MS,
)

logger = get_logger("vad_slicer")


def is_silero_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


class VadSlicer:
    """
    [UPGRADE 2.3] Silero VAD-based audio slicer.
    Cat audio thanh cac phan doan ASR (5s-30s) tai diem lang thuc su.
    """

    def __init__(
        self,
        max_segment_sec: float = MAX_ASR_SEGMENT_SEC,
        min_segment_sec: float = MIN_ASR_SEGMENT_SEC,
        vad_threshold: float = SILERO_VAD_THRESHOLD,
        min_speech_ms: int = SILERO_MIN_SPEECH_MS,
        min_silence_ms: int = SILERO_MIN_SILENCE_MS,
        pre_padding_sec: float = PRE_SPEECH_PADDING_SEC,
        post_padding_sec: float = POST_SPEECH_PADDING_SEC,
    ) -> None:
        self.max_sec = max_segment_sec
        self.min_sec = min_segment_sec
        self.vad_threshold = vad_threshold
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self.pre_padding = pre_padding_sec
        self.post_padding = post_padding_sec
        self._available = is_silero_available()
        self._model = None
        self._utils = None

        if self._available:
            self._load_model()
            if self._available and self._model is not None:
                logger.info("VadSlicer: Silero VAD ACTIVE")
            else:
                logger.info("VadSlicer: Falling back to AudioSlicer (FFmpeg silence detector)")
        else:
            logger.info("VadSlicer: Silero VAD not available — using AudioSlicer fallback.")

    @property
    def available(self) -> bool:
        return self._available and self._model is not None

    def _load_model(self) -> None:
        # Try direct ONNX / snakers4 utils first
        try:
            import sys, os
            hub_dir = Path(os.path.expanduser("~/.cache/torch/hub/snakers4_silero-vad_master"))
            src_dir = hub_dir / "src"
            if src_dir.exists() and str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))
            from silero_vad.utils_vad import init_jit_model, get_speech_timestamps, OnnxWrapper
            onnx_file = hub_dir / "src" / "silero_vad" / "data" / "silero_vad.onnx"
            if onnx_file.exists():
                self._model = OnnxWrapper(str(onnx_file), force_onnx_cpu=True)
                self._utils = (get_speech_timestamps,)
                self._available = True
                logger.debug("Silero VAD ONNX model loaded directly")
                return
        except Exception:
            pass

        # Fallback to torch hub
        try:
            import torch
            self._model, self._utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._available = True
            logger.debug("Silero VAD model loaded via torch hub")
        except Exception as exc:
            logger.debug(f"Silero VAD torch hub load failed ({exc}) — using AudioSlicer fallback.")
            self._available = False
            self._model = None

    def detect_silences(self, audio_path: Path) -> list[dict]:
        """
        [UPGRADE 2.3] Phat hien khoang lang dua tren Silero VAD.
        Tra ve list[dict] co cung format voi AudioSlicer.detect_silences().
        """
        if not self._available or self._model is None:
            return []

        try:
            import torch
            import wave
            import struct

            with wave.open(str(audio_path), "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                n_ch = wf.getnchannels()
                raw = wf.readframes(n_frames)

            samples = struct.unpack(f"<{n_frames * n_ch}h", raw)
            if n_ch > 1:
                samples = [samples[i] for i in range(0, len(samples), n_ch)]

            wav = torch.tensor(samples, dtype=torch.float32) / 32768.0

            get_speech_ts = self._utils[0]
            speech_ts = get_speech_ts(
                wav, self._model,
                threshold=self.vad_threshold,
                min_speech_duration_ms=self.min_speech_ms,
                min_silence_duration_ms=self.min_silence_ms,
                sampling_rate=sr,
            )

            silences = []
            for i in range(len(speech_ts) - 1):
                s_start = speech_ts[i]["end"] / sr
                s_end   = speech_ts[i + 1]["start"] / sr
                if s_end > s_start:
                    silences.append({
                        "start": round(s_start, 3),
                        "end":   round(s_end, 3),
                        "mid":   round((s_start + s_end) / 2.0, 3),
                    })

            logger.debug(
                f"[VadSlicer] {audio_path.name}: "
                f"{len(speech_ts)} speech / {len(silences)} silence gaps"
            )
            return silences

        except Exception as exc:
            logger.warning(f"[VadSlicer] detect_silences failed {audio_path.name}: {exc}")
            return []

    def slice_audio(self, audio_path: Path, item_id: str, output_dir: Path) -> list[dict]:
        """
        Cat audio thanh cac file WAV ASR-ready.
        Fallback sang AudioSlicer neu Silero khong co san.
        """
        if not self._available:
            from processors.audio_slicer import AudioSlicer
            return AudioSlicer(
                max_segment_sec=self.max_sec,
                min_segment_sec=self.min_sec,
                pre_padding_sec=self.pre_padding,
                post_padding_sec=self.post_padding,
            ).slice_audio(audio_path, item_id, output_dir)

        from processors.audio_converter import verify_audio
        try:
            total_duration = verify_audio(audio_path)["duration_seconds"]
        except Exception as exc:
            logger.warning(f"Cannot verify {audio_path.name}: {exc}")
            return []

        if total_duration <= self.max_sec:
            if total_duration >= self.min_sec:
                return [{"item_id": item_id, "audio_path": audio_path,
                         "duration_seconds": total_duration,
                         "segment_index": 1, "total_segments": 1}]
            return []

        silences = self.detect_silences(audio_path)

        from processors.audio_slicer import AudioSlicer
        splits = AudioSlicer(max_segment_sec=self.max_sec,
                             min_segment_sec=self.min_sec
                             ).calculate_split_points(total_duration, silences)

        if not splits or len(splits) == 1:
            if total_duration >= self.min_sec:
                return [{"item_id": item_id, "audio_path": audio_path,
                         "duration_seconds": total_duration,
                         "segment_index": 1, "total_segments": 1}]
            return []

        results = []
        output_dir.mkdir(parents=True, exist_ok=True)

        for idx, (st, en) in enumerate(splits, start=1):
            st_pad = max(0.0, round(st - self.pre_padding, 3))
            en_pad = min(total_duration, round(en + self.post_padding, 3))
            dur = round(en_pad - st_pad, 3)
            if dur < self.min_sec:
                continue

            seg_id = f"{item_id}_{idx:02d}"
            seg_path = output_dir / f"{seg_id}.wav"
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(st_pad), "-to", str(en_pad),
                "-i", str(audio_path),
                "-acodec", AUDIO_CODEC,
                "-ar", str(AUDIO_SAMPLE_RATE),
                "-ac", str(AUDIO_CHANNELS),
                "-f", "wav", str(seg_path),
            ]
            if subprocess.run(cmd, capture_output=True).returncode == 0 and seg_path.exists():
                results.append({
                    "item_id": seg_id, "audio_path": seg_path,
                    "duration_seconds": dur,
                    "segment_index": idx, "total_segments": len(splits),
                    "start_sec": st_pad, "end_sec": en_pad,
                    "vad_method": "silero",
                })

        logger.info(
            f"[VadSlicer] {audio_path.name} ({total_duration:.1f}s) "
            f"-> {len(results)} segments"
        )
        if results and audio_path.exists():
            audio_path.unlink(missing_ok=True)
        return results
