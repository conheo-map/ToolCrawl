"""
utils/tikwm_client.py — Client tích hợp TikWM API để tải Video Container thực sự từ TikTok.

Vấn đề cốt lõi: yt-dlp với `bestaudio` sẽ tải nhạc nền từ thư viện TikTok (không phải giọng nói).
Giải pháp: TikWM trả về URL video gốc (MP4 container), chứa 100% giọng nói của người sáng tạo.
"""

import urllib.request
import urllib.error
import json
import time
import random
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("tikwm_client")

# TikWM public API endpoint (miễn phí, không cần API key)
TIKWM_ENDPOINT = "https://www.tikwm.com/api/"
TIKWM_TIMEOUT = 20
TIKWM_MAX_RETRIES = 3


class TikWMClient:
    """
    Client đơn giản tích hợp TikWM API để lấy URL video gốc từ TikTok.
    TikWM trả về 2 URL riêng biệt:
        - data.play  : Video gốc MP4 chứa giọng nói thật của người tạo content
        - data.music : Bài nhạc trend đính kèm từ thư viện TikTok (KHÔNG dùng cái này!)
    """

    def __init__(self) -> None:
        self._user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
        ]

    def _get_ua(self) -> str:
        return random.choice(self._user_agents)

    def get_video_info(self, tiktok_url: str) -> dict | None:
        """
        Gọi TikWM API và trả về dict chứa:
            - play_url: URL video MP4 thực sự (chứa giọng nói)
            - music_url: URL bài nhạc trend đính kèm (CHỈ dùng để so sánh/phát hiện lỗi)
            - title: Tiêu đề video
            - author: Tên tác giả
        Trả về None nếu thất bại.
        """
        api_url = f"{TIKWM_ENDPOINT}?url={urllib.request.quote(tiktok_url, safe=':/?=&')}"

        for attempt in range(1, TIKWM_MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    api_url,
                    headers={"User-Agent": self._get_ua(), "Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=TIKWM_TIMEOUT) as resp:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)

                if data.get("code") != 0:
                    logger.warning(f"[TikWM] API returned code={data.get('code')} (attempt {attempt}/{TIKWM_MAX_RETRIES}) for {tiktok_url}")
                    if attempt < TIKWM_MAX_RETRIES:
                        time.sleep(2 * attempt)
                        continue
                    return None

                d = data.get("data", {})
                return {
                    "play_url": d.get("play"),
                    "hdplay_url": d.get("hdplay"),
                    "music_url": d.get("music"),
                    "title": d.get("title", ""),
                    "author": d.get("author", {}).get("nickname", ""),
                    "duration": d.get("duration", 0),
                }

            except urllib.error.URLError as exc:
                logger.warning(f"[TikWM] Network error (attempt {attempt}/{TIKWM_MAX_RETRIES}): {exc}")
                time.sleep(2 ** attempt)
            except Exception as exc:
                logger.warning(f"[TikWM] Error (attempt {attempt}/{TIKWM_MAX_RETRIES}): {exc}")
                time.sleep(1)

        return None

    def download_video(self, play_url: str, dest_path: Path) -> bool:
        """Tải MP4 video trực tiếp từ CDN URL về dest_path với retry và chunked stream."""
        for attempt in range(1, TIKWM_MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    play_url,
                    headers={
                        "User-Agent": self._get_ua(),
                        "Referer": "https://www.tiktok.com/",
                        "Accept": "*/*",
                    }
                )
                with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as out_f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        out_f.write(chunk)

                if dest_path.exists() and dest_path.stat().st_size > 10_000:
                    return True
            except Exception as exc:
                logger.warning(f"[TikWM] Download attempt {attempt}/{TIKWM_MAX_RETRIES} failed: {exc}")
                time.sleep(2 * attempt)

        logger.error(f"[TikWM] Download completely failed for {play_url[:60]}")
        return False
