"""
processors/speech_transcriber.py — Tự động sinh transcript tiếng Việt nháp (Bước 05).
Chạy ngầm bằng faster-whisper CPU int8, lưu transcript vào thư mục transcripts/ trên Local.
"""

import sys
import json
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("speech_transcriber")


class SpeechTranscriber:
    """
    Sinh bản transcript nháp ~70-85% cho audio bằng faster-whisper.
    Hoạt động độc lập và lưu file văn bản vào thư mục transcripts/ trên Local.
    """

    _model = None

    def __init__(self, model_size: str = "tiny") -> None:
        self._model_size = model_size

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            try:
                from faster_whisper import WhisperModel
                cls._model = WhisperModel("tiny", device="cpu", compute_type="int8")
                logger.info("[SpeechTranscriber] faster-whisper initialized for local draft transcription")
            except Exception as exc:
                logger.debug(f"[SpeechTranscriber] faster-whisper not available: {exc}")
                cls._model = False
        return cls._model

    def transcribe_file(self, audio_path: Path, output_dir: Path | None = None) -> dict:
        """
        Phiên âm file audio và lưu file text vào output_dir.
        Trả về dict: {"text": str, "segments": list, "word_count": int, "path": str}
        """
        if not audio_path.exists():
            return {"text": "", "word_count": 0}

        model = self._get_model()
        if not model or model is False:
            return {"text": "", "word_count": 0}

        try:
            segments, info = model.transcribe(
                str(audio_path),
                language="vi",
                vad_filter=True,
                beam_size=1,
            )

            full_text_list = []
            segment_list = []
            for seg in segments:
                clean_seg_text = seg.text.strip()
                if clean_seg_text:
                    full_text_list.append(clean_seg_text)
                    segment_list.append({
                        "start": round(seg.start, 2),
                        "end": round(seg.end, 2),
                        "text": clean_seg_text
                    })

            full_text = " ".join(full_text_list)
            word_count = len(full_text.split())

            # Lưu file .txt và .json transcript trên Local
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                txt_file = output_dir / f"{audio_path.stem}.txt"
                json_file = output_dir / f"{audio_path.stem}.json"

                txt_file.write_text(full_text, encoding="utf-8")
                json_file.write_text(
                    json.dumps({
                        "item_id": audio_path.stem,
                        "duration_seconds": round(info.duration, 2),
                        "language": "vi",
                        "word_count": word_count,
                        "text": full_text,
                        "segments": segment_list
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

            logger.debug(f"[SpeechTranscriber] Generated transcript for {audio_path.name}: {word_count} words")
            return {
                "text": full_text,
                "word_count": word_count,
                "segments": segment_list,
                "txt_path": str(output_dir / f"{audio_path.stem}.txt") if output_dir else None
            }

        except Exception as exc:
            logger.debug(f"[SpeechTranscriber] Transcription failed for {audio_path.name}: {exc}")
            return {"text": "", "word_count": 0}
