"""
processors/speech_transcriber.py — Tự động sinh transcript tiếng Việt nháp (Bước 05).
Chạy ngầm bằng faster-whisper CPU int8, lưu transcript vào thư mục transcripts/ trên Local.
"""

import sys
import json
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("speech_transcriber")


def _format_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp: 00:00:05,120"""
    millis = int((seconds - int(seconds)) * 1000)
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


class SpeechTranscriber:
    """
    Sinh bản transcript nháp ~70-85% cho audio bằng faster-whisper.
    Tạo cả file text (.txt), word timestamps (.json) và phụ đề chuẩn (.srt).
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
        Phiên âm file audio và lưu file text/json/srt vào output_dir.
        Trả về dict: {"text": str, "segments": list, "word_count": int, "speaker_type": str}
        """
        if not audio_path.exists():
            return {"text": "", "word_count": 0, "speaker_type": "monologue"}

        model = self._get_model()
        if not model or model is False:
            return {"text": "", "word_count": 0, "speaker_type": "monologue"}

        try:
            segments, info = model.transcribe(
                str(audio_path),
                language="vi",
                vad_filter=True,
                word_timestamps=True,
                beam_size=1,
            )

            full_text_list = []
            segment_list = []
            srt_lines = []
            idx = 1

            for seg in segments:
                clean_seg_text = seg.text.strip()
                if clean_seg_text:
                    full_text_list.append(clean_seg_text)
                    words_meta = []
                    if hasattr(seg, "words") and seg.words:
                        for w in seg.words:
                            words_meta.append({
                                "word": w.word.strip(),
                                "start": round(w.start, 2),
                                "end": round(w.end, 2),
                                "probability": round(w.probability, 2),
                            })

                    segment_list.append({
                        "id": idx,
                        "start": round(seg.start, 2),
                        "end": round(seg.end, 2),
                        "text": clean_seg_text,
                        "words": words_meta,
                    })

                    srt_lines.append(f"{idx}\n{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}\n{clean_seg_text}\n")
                    idx += 1

            full_text = " ".join(full_text_list)
            word_count = len(full_text.split())

            # Phát hiện Monologue hay Dialogue dựa trên số lượng ngắt đoạn và khoảng cách
            speaker_type = "dialogue" if len(segment_list) >= 4 and any((segment_list[i]["start"] - segment_list[i-1]["end"]) > 1.2 for i in range(1, len(segment_list))) else "monologue"

            # Lưu file .txt, .json và .srt transcript trên Local
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                txt_file = output_dir / f"{audio_path.stem}.txt"
                json_file = output_dir / f"{audio_path.stem}.json"
                srt_file = output_dir / f"{audio_path.stem}.srt"

                txt_file.write_text(full_text, encoding="utf-8")
                srt_file.write_text("\n".join(srt_lines), encoding="utf-8")
                json_file.write_text(
                    json.dumps({
                        "item_id": audio_path.stem,
                        "duration_seconds": round(info.duration, 2),
                        "language": "vi",
                        "speaker_type": speaker_type,
                        "word_count": word_count,
                        "text": full_text,
                        "segments": segment_list,
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            logger.debug(f"[SpeechTranscriber] Generated transcript & SRT for {audio_path.name}: {word_count} words ({speaker_type})")
            return {
                "text": full_text,
                "word_count": word_count,
                "speaker_type": speaker_type,
                "segments": segment_list,
                "txt_path": str(output_dir / f"{audio_path.stem}.txt") if output_dir else None,
            }

        except Exception as exc:
            logger.debug(f"[SpeechTranscriber] Transcription failed for {audio_path.name}: {exc}")
            return {"text": "", "word_count": 0, "speaker_type": "monologue"}

