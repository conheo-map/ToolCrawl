"""
tiktok_crawler.py — High-Performance Audio Downloader from URLs
================================================================
Tải luồng âm thanh video thực sự từ TikTok / mạng xã hội / URL trực tiếp.
Tích hợp TikWM API, yt-dlp fallback và hỗ trợ cả tệp video/audio cục bộ.
"""
import subprocess
import tempfile
import urllib.request
import urllib.parse
import json
import time
import random
from pathlib import Path
from typing import Dict, Optional
import yt_dlp


class TikTokCrawler:
    def __init__(self, raw_dir: Path, cookies_file: Optional[Path] = None):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = cookies_file
        self._user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ]

    def _get_ua(self) -> str:
        return random.choice(self._user_agents)

    def _download_via_tikwm(self, url: str, out_wav: Path) -> bool:
        """Tải trực tiếp qua TikWM API để tránh bị chặn IP và bóc đúng giọng nói."""
        try:
            api_endpoint = "https://www.tikwm.com/api/"
            post_data = urllib.parse.urlencode({"url": url, "hd": 1}).encode("utf-8")
            req = urllib.request.Request(
                api_endpoint,
                data=post_data,
                headers={
                    "User-Agent": self._get_ua(),
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                }
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("code") == 0:
                d = data.get("data", {})
                play_url = d.get("play") or d.get("hdplay")
                if play_url:
                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_f:
                        tmp_mp4 = Path(tmp_f.name)

                    try:
                        down_req = urllib.request.Request(
                            play_url,
                            headers={
                                "User-Agent": self._get_ua(),
                                "Referer": "https://www.tiktok.com/",
                            }
                        )
                        with urllib.request.urlopen(down_req, timeout=30) as d_resp, open(tmp_mp4, "wb") as f_out:
                            while True:
                                chunk = d_resp.read(65536)
                                if not chunk:
                                    break
                                f_out.write(chunk)

                        if tmp_mp4.exists() and tmp_mp4.stat().st_size > 1000:
                            # Convert sang 16kHz mono WAV bằng ffmpeg
                            cmd = [
                                "ffmpeg", "-y", "-i", str(tmp_mp4),
                                "-ar", "16000", "-ac", "1",
                                "-acodec", "pcm_s16le", str(out_wav)
                            ]
                            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                            return out_wav.exists() and out_wav.stat().st_size > 1000
                    finally:
                        tmp_mp4.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    def download_url(self, url: str) -> Optional[Dict]:
        """
        Tải video/audio từ URL (hoặc nạp tệp cục bộ) và trích xuất thành 16kHz mono WAV.
        """
        item_id = url.split("?")[0].rstrip("/").split("/")[-1]
        if not item_id or not item_id.isdigit():
            import hashlib
            item_id = hashlib.md5(url.encode()).hexdigest()[:16]
        item_id = f"tt_{item_id}"
        out_wav = self.raw_dir / f"{item_id}.wav"

        if out_wav.exists() and out_wav.stat().st_size > 1000:
            return {"item_id": item_id, "audio_path": out_wav, "url": url}

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        # 0. Nếu là đường dẫn tệp âm thanh / video có sẵn trên máy
        local_p = Path(url).resolve()
        if not local_p.exists():
            local_p = Path(__file__).resolve().parent.parent.parent / url

        if local_p.exists() and local_p.is_file():
            try:
                import soundfile as sf
                import torchaudio
                import torch
                data, sr = sf.read(str(local_p), dtype="float32")
                if data.ndim > 1:
                    data = data.mean(axis=1)
                if sr != 16000:
                    resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
                    tensor = torch.from_numpy(data).unsqueeze(0)
                    data = resampler(tensor).squeeze(0).numpy()
                data = np.clip(data, -1.0, 1.0)
                sf.write(str(out_wav), data, 16000, subtype="PCM_16")
                if out_wav.exists() and out_wav.stat().st_size > 1000:
                    return {"item_id": item_id, "audio_path": out_wav, "url": url}
            except Exception:
                cmd = [
                    "ffmpeg", "-y", "-i", str(local_p),
                    "-ar", "16000", "-ac", "1",
                    "-acodec", "pcm_s16le", str(out_wav)
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                if out_wav.exists() and out_wav.stat().st_size > 1000:
                    return {"item_id": item_id, "audio_path": out_wav, "url": url}


        # 1. Thử tải qua TikWM trước (vượt block IP TikTok & lấy đúng giọng nói gốc)
        if "tiktok.com" in url:
            if self._download_via_tikwm(url, out_wav):
                return {"item_id": item_id, "audio_path": out_wav, "url": url}

        # 2. Tải trực tiếp bằng urllib nếu là link tệp âm thanh / video trực tiếp (.mp3, .wav, .mp4)
        if url.startswith("http") and any(url.lower().endswith(ext) or ext + "?" in url.lower() for ext in [".mp3", ".wav", ".m4a", ".mp4", ".aac"]):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self._get_ua()})
                with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tmp_f:
                    tmp_p = Path(tmp_f.name)
                with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_p, "wb") as f_out:
                    f_out.write(resp.read())
                if tmp_p.exists() and tmp_p.stat().st_size > 1000:
                    cmd = [
                        "ffmpeg", "-y", "-i", str(tmp_p),
                        "-ar", "16000", "-ac", "1",
                        "-acodec", "pcm_s16le", str(out_wav)
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    tmp_p.unlink(missing_ok=True)
                    if out_wav.exists() and out_wav.stat().st_size > 1000:
                        return {"item_id": item_id, "audio_path": out_wav, "url": url}
            except Exception:
                pass

        # 3. Fallback sang yt-dlp
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(self.raw_dir / f"{item_id}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "user_agent": self._get_ua(),
            "referer": "https://www.tiktok.com/",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }],
            "postprocessor_args": [
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "pcm_s16le",
            ],
        }
        if self.cookies_file and self.cookies_file.exists():
            ydl_opts["cookiefile"] = str(self.cookies_file)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if out_wav.exists() and out_wav.stat().st_size > 1000:
                return {"item_id": item_id, "audio_path": out_wav, "url": url}
        except Exception:
            pass
        return None
