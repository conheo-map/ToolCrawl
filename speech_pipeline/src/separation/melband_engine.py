"""
melband_engine.py — High-Fidelity Vocal Separator Engine
=========================================================
Tách vocal chất lượng phòng thu (Studio High-Fidelity) với đa ca lấy mẫu (shifts=2, overlap=0.5).
Tối ưu hóa GPU VRAM, xử lý pure SoundFile I/O không phụ thuộc torchcodec.
"""
from pathlib import Path
import soundfile as sf
import numpy as np
import torch
import torchaudio
from demucs.apply import apply_model
from demucs.pretrained import get_model


class MelbandRoformerEngine:
    def __init__(self, model_name: str = "htdemucs", device: str = None, shifts: int = 2, overlap: float = 0.5):
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        self.model_name = model_name
        self.shifts = shifts
        self.overlap = overlap
        self.model = None
        self._init_model()

    def _init_model(self):
        try:
            self.model = get_model(self.model_name)
        except Exception:
            self.model = get_model("htdemucs")
        self.model.to(self.device)
        self.model.eval()

    def separate_vocal(self, audio_path: Path, output_path: Path) -> bool:
        """
        Tách lấy vocal stem chất lượng cao và lưu thành 16kHz mono 16-bit PCM WAV.
        """
        try:
            data, sr = sf.read(str(audio_path), dtype="float32")
            if data.ndim == 1:
                wav = torch.from_numpy(data).unsqueeze(0)
            else:
                wav = torch.from_numpy(data.T)

            if sr != self.model.samplerate:
                resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=self.model.samplerate)
                wav = resampler(wav)
                sr = self.model.samplerate

            if wav.shape[0] == 1:
                wav = wav.repeat(2, 1)

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

            vocal_idx = self.model.sources.index("vocals") if "vocals" in self.model.sources else 3
            vocal = sources[0, vocal_idx]
            vocal = vocal * ref.std() + ref.mean()

            vocal_mono = vocal.mean(dim=0, keepdim=True).cpu()
            if sr != 16000:
                resampler_16k = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
                vocal_mono = resampler_16k(vocal_mono)

            vocal_np = vocal_mono.squeeze(0).numpy()
            vocal_np = np.clip(vocal_np, -1.0, 1.0)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(output_path), vocal_np, 16000, subtype="PCM_16")

            if self.device == "cuda":
                torch.cuda.empty_cache()

            return True
        except Exception as e:
            print(f"[MelbandRoformerEngine Error] {audio_path.name}: {e}")
            if self.device == "cuda":
                torch.cuda.empty_cache()
            return False
