"""
processors/transcription_broker.py — Cache kết quả Whisper, tái dùng qua toàn pipeline.

Vấn đề giải quyết:
  Trước đây mỗi video bị transcribe 3 lần độc lập:
    1. SpeechMaster._assess_raw_quality() — Whisper pre-gate
    2. SpeechMaster._run_asr_quality_gate() — Whisper post-gate
    3. RegionClassifier._transcribe_audio_snippet() — Phân vùng giọng

  Broker này cache kết quả theo (path, model_size, max_duration_s).
  SpeechMaster, RegionClassifier, QC Evaluator chia sẻ chung một broker,
  giảm từ 3 -> 1 lần Whisper inference thực tế per video.
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from utils.logger import get_logger
from utils.model_registry import ModelRegistry

logger = get_logger("transcription_broker")


@dataclass
class TranscriptResult:
    """
    Kết quả transcription đầy đủ từ Whisper.
    Được cache và tái dùng qua tất cả component cần transcript.
    """
    text: str = ""
    avg_logprob: float = -1.0
    no_speech_prob: float = 1.0
    language: str = "vi"
    segments: list = field(default_factory=list)
    word_count: int = 0
    success: bool = False
    error: str = ""

    @property
    def is_good_quality(self) -> bool:
        """Kiểm tra kết quả có chất lượng tốt không (avg_logprob cao, có text)."""
        return (
            self.success
            and len(self.text.strip()) >= 5
            and self.avg_logprob >= -0.7
            and self.no_speech_prob <= 0.4
        )

    @property
    def quality_grade(self) -> str:
        """Phân loại chất lượng: 'good' / 'degraded' / 'none'."""
        if not self.success or not self.text.strip():
            return "none"
        if self.avg_logprob >= -0.5 and self.no_speech_prob <= 0.3:
            return "good"
        if self.avg_logprob >= -0.8 and self.no_speech_prob <= 0.6:
            return "degraded"
        return "none"


class TranscriptionBroker:
    """
    Cache trung tâm cho kết quả Whisper.
    Mỗi (audio_path, model_size, max_duration_s) chỉ được transcribe 1 lần.
    Thread-safe: nhiều worker có thể gọi đồng thời.
    """

    def __init__(self) -> None:
        self._cache: dict[str, TranscriptResult] = {}
        self._lock = threading.Lock()

    def _make_key(self, path: Path, model_size: str, max_duration_s: float) -> str:
        return f"{path}::{model_size}::{max_duration_s:.1f}"

    def get_or_transcribe(
        self,
        path: Path,
        model_size: str = "base",
        max_duration_s: float = 30.0,
        language: str = "vi",
    ) -> TranscriptResult:
        """
        Lấy transcript từ cache, nếu chưa có thì transcribe và cache kết quả.
        """
        cache_key = self._make_key(path, model_size, max_duration_s)

        with self._lock:
            if cache_key in self._cache:
                logger.debug(f"[Broker] Cache hit: {path.name} ({model_size})")
                return self._cache[cache_key]

        result = self._do_transcribe(path, model_size, max_duration_s, language)

        with self._lock:
            self._cache[cache_key] = result

        return result

    def _do_transcribe(
        self,
        path: Path,
        model_size: str,
        max_duration_s: float,
        language: str,
    ) -> TranscriptResult:
        """Thực hiện Whisper transcription thực tế."""
        if not path.exists():
            return TranscriptResult(error=f"File not found: {path}", success=False)

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return TranscriptResult(error="faster_whisper not installed", success=False)

        def _load_whisper():
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            logger.info(f"[Broker] Loading Whisper {model_size} on {device}")
            return WhisperModel(model_size, device=device, compute_type=compute_type)

        try:
            with ModelRegistry.gpu_semaphore:
                model = ModelRegistry.get(f"whisper_{model_size}", _load_whisper)
                logger.debug(f"[Broker] Transcribing: {path.name} ({model_size}, max={max_duration_s}s)")
                segments_raw, info = model.transcribe(
                    str(path),
                    language=language,
                    clip_timestamps=f"0,{int(max_duration_s)}",
                    word_timestamps=False,
                )

            segments = list(segments_raw)
            text = " ".join(seg.text.strip() for seg in segments)

            if segments:
                avg_logprob = sum(getattr(seg, 'avg_logprob', -1.0) for seg in segments) / len(segments)
                no_speech_prob = sum(getattr(seg, 'no_speech_prob', 0.5) for seg in segments) / len(segments)
            else:
                avg_logprob = -1.0
                no_speech_prob = 1.0

            return TranscriptResult(
                text=text.strip(),
                avg_logprob=round(avg_logprob, 4),
                no_speech_prob=round(no_speech_prob, 4),
                language=info.language if hasattr(info, 'language') else language,
                segments=[{"text": seg.text, "start": seg.start, "end": seg.end} for seg in segments],
                word_count=len(text.split()),
                success=True,
            )
        except Exception as exc:
            import traceback
            logger.warning(f"[Broker] Transcription failed for {path.name}: {exc}\n{traceback.format_exc()}")
            return TranscriptResult(error=str(exc), success=False)

    def invalidate(self, path: Path) -> None:
        """Xóa cache của một file cụ thể (khi file đã được xử lý lại)."""
        with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(str(path) + "::")]
            for k in keys_to_del:
                del self._cache[k]

    def clear(self) -> None:
        """Xóa toàn bộ cache."""
        with self._lock:
            self._cache.clear()

    @property
    def cache_size(self) -> int:
        """Số lượng kết quả đang được cache."""
        with self._lock:
            return len(self._cache)