"""
tiktok_crawler.py — High-Performance Audio Downloader from URLs
================================================================
"""
from pathlib import Path
from typing import List, Dict, Optional
import yt_dlp


class TikTokCrawler:
    def __init__(self, raw_dir: Path, cookies_file: Optional[Path] = None):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = cookies_file

    def download_url(self, url: str) -> Optional[Dict]:
        """
        Tải video thô và trích xuất thành 16kHz mono WAV.
        """
        item_id = url.split("?")[0].rstrip("/").split("/")[-1]
        if not item_id or not item_id.isdigit():
            import hashlib
            item_id = hashlib.md5(url.encode()).hexdigest()[:16]
        item_id = f"tt_{item_id}"
        out_wav = self.raw_dir / f"{item_id}.wav"

        if out_wav.exists() and out_wav.stat().st_size > 1000:
            return {"item_id": item_id, "audio_path": out_wav, "url": url}

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(self.raw_dir / f"{item_id}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
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
