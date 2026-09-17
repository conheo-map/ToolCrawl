"""
demucs_engine.py — Hybrid Transformer Demucs Vocal Separation Engine
===================================================================
Tách vocal bằng mô hình Meta AI Demucs v4 (htdemucs).
Tối ưu hóa GPU VRAM, xử lý batching và tự động giải phóng bộ nhớ.
"""
from pathlib import Path
import torch
import torchaudio
from demucs.apply import apply_model
from demucs.pretrained import get_model


class DemucsEngine:
    def __init__(self, model_name: str = "htdemucs", device: str = None, shifts: int = 1, overlap: float = 0.25):
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.shifts = shifts
        self.overlap = overlap
        self.model = get_model(model_name)
        self.model.to(self.device)
        self.model.eval()

    def separate_vocal(self, audio_path: Path, output_path: Path) -> bool:
        """
        Tách lấy vocal stem từ audio_path và lưu vào output_path.
        """
        try:
            wav, sr = torchaudio.load(str(audio_path))
            
            # Resample sang sample rate của Demucs (44.1kHz) nếu cần
            if sr != self.model.samplerate:
                resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=self.model.samplerate)
                wav = resampler(wav)
                sr = self.model.samplerate

            # Chuyển sang stereo nếu mono
            if wav.shape[0] == 1:
                wav = wav.repeat(2, 1)

            # Đưa vào GPU và chuẩn hóa batch [1, channels, samples]
            ref = wav.mean(0)
            wav = (wav - ref.mean()) / (ref.std() + 1e-8)
            wav = wav.unsqueeze(0).to(self.device)

            with torch.no_grad():
                sources = apply_model(
                    self.model,
                    wav,
                    shifts=self.shifts,
                    overlap=self.overlap,
                    progress=False,
                    num_workers=0
                )

            # Lấy track vocal (index 3 trong htdemucs: drums, bass, other, vocals)
            vocal_idx = self.model.sources.index("vocals") if "vocals" in self.model.sources else 3
            vocal = sources[0, vocal_idx]
            vocal = vocal * ref.std() + ref.mean()

            # Resample về 16kHz mono chuẩn huấn luyện ASR
            vocal_mono = vocal.mean(dim=0, keepdim=True).cpu()
            if sr != 16000:
                resampler_16k = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
                vocal_mono = resampler_16k(vocal_mono)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(str(output_path), vocal_mono, 16000, encoding="PCM_S", bits_per_sample=16)

            # Giải phóng VRAM
            if self.device == "cuda":
                torch.cuda.empty_cache()

            return True
        except Exception as e:
            print(f"[DemucsEngine Error] {audio_path.name}: {e}")
            if self.device == "cuda":
                torch.cuda.empty_cache()
            return False
