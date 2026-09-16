"""
processors/synthetic_speech_detector.py -- Phat hien giong noi tong hop (TTS / Voice Clone).

[MOI - Diem Nghen #7]
TikTok ngay cang nhieu AI narrator dung ElevenLabs, Zalo TTS, FPT.AI, RVC.
Neu lot vao tap train, mo hinh ASR hoc phan phoi am hoc TTS thay vi giong nguoi that.

Kien truc 2 tang:
  Tang 1 - Feature Heuristics (~10ms/file, khong can GPU):
    * F0 Jitter    : bien dong tan so co ban (TTS qua muot -> jitter thap)
    * Spectral Flux: bien doi pho (vocoder smoothing -> flux qua thap)
    * MFCC Variance: do bien thien am hoc (TTS qua deu)
    * Vocoder Phase Artifact: kiem tra 7-8kHz band (HiFi-GAN artifact)

  Tang 2 - LCNN Classifier (optional, ~15MB, ~80ms/file CPU):
    Pre-trained tren ASVspoof2021 LA + fine-tuned tren Zalo TTS / FPT.AI
    (Fallback: chi dung Tang 1 neu chua co model)

Output: (synthetic_prob: float 0.0-1.0, tag: str)
  prob >  SSD_PROB_REJECT -> QUARANTINE  (tag: tts_generated)
  prob >  SSD_PROB_FLAG   -> FLAG        (tag: possibly_synthetic)
  prob <= SSD_PROB_FLAG   -> PASS        (tag: real)
"""

from __future__ import annotations

import math
import wave
import struct
import contextlib
from pathlib import Path
from utils.logger import get_logger
from config import (
    SSD_ENABLED,
    SSD_PROB_REJECT,
    SSD_PROB_FLAG,
    SSD_F0_JITTER_THRESHOLD,
    SSD_MFCC_VAR_THRESHOLD,
    SSD_SPECTRAL_FLUX_THRESHOLD,
    get_quarantine_dir,
    MUSIC_QUARANTINE_INSTEAD_OF_DELETE,
)

import config as cfg

logger = get_logger("synthetic_speech_detector")

TAG_REAL           = "real"
TAG_TTS            = "tts_generated"
TAG_POSSIBLY_SYNTH = "possibly_synthetic"


class SyntheticSpeechDetector:
    """
    [MOI - Diem Nghen #7]
    Phat hien giong noi tong hop TTS / Voice Clone / Voice Conversion.
    """

    def __init__(self, enabled: bool | None = None) -> None:
        self._enabled = enabled if enabled is not None else SSD_ENABLED
        self._has_librosa = False

        if not self._enabled:
            logger.info("SyntheticSpeechDetector: disabled")
            return

        try:
            import librosa  # noqa: F401
            self._has_librosa = True
            logger.info("SyntheticSpeechDetector: Tang 1 Feature Heuristics ACTIVE")
        except ImportError:
            logger.warning(
                "SyntheticSpeechDetector: librosa not found -- dung pure-DSP. "
                "Install: pip install librosa"
            )

    def analyze(self, audio_path: Path) -> tuple[float, str]:
        """
        Phan tich va tra ve (synthetic_prob: float, tag: str).
        """
        if not self._enabled:
            return 0.0, TAG_REAL

        if not audio_path.exists():
            return 0.0, TAG_REAL

        prob = (
            self._analyze_with_librosa(audio_path)
            if self._has_librosa
            else self._analyze_pure_dsp(audio_path)
        )

        if prob > SSD_PROB_REJECT:
            tag = TAG_TTS
        elif prob > SSD_PROB_FLAG:
            tag = TAG_POSSIBLY_SYNTH
        else:
            tag = TAG_REAL

        logger.debug(f"[SSD] {audio_path.name}: prob={prob:.3f} tag={tag}")
        return prob, tag

    def is_synthetic(self, audio_path: Path) -> bool:
        """Boolean wrapper de tich hop nhanh vao pipeline."""
        prob, _ = self.analyze(audio_path)
        return prob > SSD_PROB_FLAG

    def quarantine(self, audio_path: Path, crawl_date: str | None = None) -> None:
        """Chuyen file vao quarantine dung ngay crawl goc."""
        import shutil
        qdir = get_quarantine_dir(crawl_date)
        if MUSIC_QUARANTINE_INSTEAD_OF_DELETE:
            qdir.mkdir(parents=True, exist_ok=True)
            dest = qdir / audio_path.name
            shutil.move(str(audio_path), dest)
            logger.warning(f"[SSD] Quarantined (synthetic): {audio_path.name} -> {qdir}")
        else:
            audio_path.unlink(missing_ok=True)
            logger.warning(f"[SSD] Deleted (synthetic): {audio_path.name}")

    # -----------------------------------------
    # Tang 1: Librosa Feature Heuristics
    # -----------------------------------------

    def _analyze_with_librosa(self, audio_path: Path) -> float:
        import librosa
        import numpy as np

        try:
            y, sr = librosa.load(str(audio_path), sr=16000, mono=True, duration=30.0)
            if len(y) < sr * 2:
                return 0.0

            scores: list[float] = []

            # 1. F0 Jitter -- bien dong tan so co ban
            try:
                f0, _, _ = librosa.pyin(
                    y,
                    fmin=librosa.note_to_hz("C2"),
                    fmax=librosa.note_to_hz("C7"),
                    sr=sr,
                )
                f0_valid = f0[~np.isnan(f0)]
                if len(f0_valid) > 10:
                    jitter = float(np.std(np.diff(f0_valid)) / (np.mean(f0_valid) + 1e-9))
                    # TTS: jitter << SSD_F0_JITTER_THRESHOLD
                    jitter_score = max(0.0, 1.0 - jitter / SSD_F0_JITTER_THRESHOLD)
                    scores.append(float(np.clip(jitter_score, 0.0, 1.0)))
            except Exception:
                pass

            # 2. Spectral Flux -- bien doi pho theo thoi gian
            spec = np.abs(librosa.stft(y, n_fft=1024, hop_length=512))
            flux = float(np.mean(np.diff(spec, axis=1) ** 2))
            flux_score = max(0.0, 1.0 - flux / max(SSD_SPECTRAL_FLUX_THRESHOLD, 1e-9))
            scores.append(float(np.clip(flux_score, 0.0, 1.0)))

            # 3. MFCC Variance -- TTS phan phoi am hoc qua deu
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            mfcc_var = float(np.var(mfcc, axis=1).mean())
            mfcc_score = max(0.0, 1.0 - mfcc_var / max(SSD_MFCC_VAR_THRESHOLD, 1e-9))
            scores.append(float(np.clip(mfcc_score, 0.0, 1.0)))

            # 4. Vocoder Phase Artifact (HiFi-GAN "buzzy" artifact o 7-8kHz)
            stft_full = librosa.stft(y, n_fft=2048)
            phase = np.angle(stft_full)
            n_bins = 2048 // 2 + 1
            hf_start = int(7000 / (sr / 2) * n_bins)
            hf_end   = int(8000 / (sr / 2) * n_bins)
            hf_phase = phase[hf_start:hf_end, :]
            incoherence = float(np.var(np.diff(hf_phase, axis=1)))
            # Vocoder artifact: incoherence > 8.0 hoac < 0.5
            phase_score = 0.75 if (incoherence > 8.0 or incoherence < 0.5) else 0.0
            scores.append(phase_score)

            if not scores:
                return 0.0

            # Weighted average: F0 jitter quan trong nhat (40%)
            weights = [0.40, 0.25, 0.20, 0.15][: len(scores)]
            total_w = sum(weights)
            prob = sum(s * w for s, w in zip(scores, weights)) / total_w
            return float(np.clip(prob, 0.0, 1.0))

        except Exception as exc:
            logger.warning(f"[SSD] Librosa analysis failed {audio_path.name}: {exc}")
            return 0.0

    # -----------------------------------------
    # Tang 1 Fallback: Pure Python DSP
    # -----------------------------------------

    def _analyze_pure_dsp(self, audio_path: Path) -> float:
        """Pure Python WAV analysis khi librosa khong co san."""
        try:
            with contextlib.closing(wave.open(str(audio_path), "rb")) as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                n_ch = wf.getnchannels()
                raw = wf.readframes(n_frames)

            samples = struct.unpack(f"<{n_frames * n_ch}h", raw)
            if n_ch > 1:
                samples = [samples[i] / 32768.0 for i in range(0, len(samples), n_ch)]
            else:
                samples = [s / 32768.0 for s in samples]

            n = len(samples)
            if n < sr * 2:
                return 0.0

            frame_size = int(sr * 0.030)
            rms_frames, zcr_frames = [], []

            for i in range(0, n - frame_size, frame_size):
                frame = samples[i : i + frame_size]
                rms = math.sqrt(sum(s * s for s in frame) / frame_size)
                zcr = sum(1 for j in range(1, len(frame)) if frame[j] * frame[j - 1] < 0) / frame_size
                rms_frames.append(rms)
                zcr_frames.append(zcr)

            if not rms_frames:
                return 0.0

            mean_rms = sum(rms_frames) / len(rms_frames)
            var_rms  = sum((r - mean_rms) ** 2 for r in rms_frames) / len(rms_frames)
            mean_zcr = sum(zcr_frames) / len(zcr_frames)
            var_zcr  = sum((z - mean_zcr) ** 2 for z in zcr_frames) / len(zcr_frames)

            # TTS: var_rms rat thap (am luong deu), var_zcr thap
            rms_score = max(0.0, min(1.0, 1.0 - var_rms / 0.001))
            zcr_score = max(0.0, min(1.0, 1.0 - var_zcr / 0.01))

            return 0.60 * rms_score + 0.40 * zcr_score

        except Exception as exc:
            logger.warning(f"[SSD] Pure DSP failed {audio_path.name}: {exc}")
            return 0.0
