"""
crawlers/tiktok.py — TikTokCrawler: search + metadata extraction + download.
"""

import re
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime, timezone, timedelta

import yt_dlp

from crawlers.base import BaseCrawler, DownloadError
from utils.logger import get_logger
from config import TIKTOK_COOKIES_FILE, make_batch_id, BASE_OUTPUT_DIR

logger = get_logger("tiktok_crawler")
VN_TZ = timezone(timedelta(hours=7))

TIKTOK_VIDEO_PATTERN = re.compile(
    r'(?:https?://(?:www\.)?tiktok\.com)?/@([A-Za-z0-9._%-]+)/video/(\d{8,19})'
)


class TikTokCrawler(BaseCrawler):
    PLATFORM = "tiktok"
    ID_PREFIX = "tt"

    def __init__(self, cookies_file: Path | None = TIKTOK_COOKIES_FILE, **kwargs):
        super().__init__(cookies_file=cookies_file, **kwargs)

    def search(self, keyword: str, max_results: int = 200) -> list[str]:
        """
        Tìm kiếm video TikTok theo keyword.
        Thử yt-dlp native search trước, fallback sang HTML scrape.
        """
        urls: list[str] = []

        # Phương pháp 1: yt-dlp native search
        try:
            urls = self._search_via_ytdlp(keyword, max_results)
            if urls:
                logger.info(f"[TikTok] yt-dlp search: {len(urls)} URLs for '{keyword}'")
                return urls[:max_results]
        except Exception as exc:
            logger.warning(f"[TikTok] yt-dlp search failed: {exc} — fallback to HTML")

        # Phương pháp 2: HTML scrape
        try:
            urls = self._search_via_html(keyword, max_results)
            logger.info(f"[TikTok] HTML scrape: {len(urls)} URLs for '{keyword}'")
        except Exception as exc:
            logger.error(f"[TikTok] Both search methods failed for '{keyword}': {exc}")

        return urls[:max_results]

    def crawl_url(self, url: str, batch_num: int = 1) -> dict | None:
        """
        Crawl một URL TikTok:
          1. Download + convert audio
          2. Build record JSON theo spec
        Trả về None nếu lỗi.
        """
        item_id = self._extract_item_id(url)
        if not item_id:
            logger.warning(f"Cannot extract item_id from URL: {url}")
            return None

        try:
            result = self.download_audio(url, item_id)
            info_dict = result.get("info_dict", {})
            duration = result["duration_seconds"]
            audio_path: Path = result["audio_path"]

            record = self._build_record(
                url=url,
                item_id=item_id,
                info_dict=info_dict,
                audio_path=audio_path,
                duration=duration,
                batch_num=batch_num,
            )
            return record

        except DownloadError as exc:
            logger.error(f"[TikTok] Download failed for {item_id}: {exc}")
            return None
        except Exception as exc:
            logger.error(f"[TikTok] Unexpected error for {item_id}: {exc}")
            return None

    # ─────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────

    def _search_via_ytdlp(self, keyword: str, max_results: int) -> list[str]:
        """Dùng yt-dlp tiktoksearch extractor."""
        search_query = f"tiktoksearch{max_results}:{keyword}"
        opts = self._build_ydl_opts(download=False)
        opts["extract_flat"] = True
        opts["quiet"] = True

        urls = []
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search_query, download=False) or {}
            entries = info.get("entries", [])
            for entry in entries:
                url = entry.get("url") or entry.get("webpage_url")
                if url and "tiktok.com" in url:
                    urls.append(url)
        return urls

    def _search_via_html(self, keyword: str, max_results: int) -> list[str]:
        """Scrape search page HTML và extract URLs bằng regex."""
        search_url = "https://www.tiktok.com/search/video?q=" + quote_plus(keyword)
        opts = self._build_ydl_opts(download=False)
        opts["quiet"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            response = ydl.urlopen(search_url)
            html = response.read().decode("utf-8", "replace")

        html = html.replace(r"\/", "/").replace(r"\u002F", "/")
        seen = set()
        urls = []
        for username, video_id in TIKTOK_VIDEO_PATTERN.findall(html):
            url = f"https://www.tiktok.com/@{username}/video/{video_id}"
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def _extract_item_id(self, url: str) -> str | None:
        """Extract item_id dạng tt_<video_id> từ URL."""
        m = TIKTOK_VIDEO_PATTERN.search(url)
        if m:
            return f"tt_{m.group(2)}"
        return None

    def _build_record(
        self,
        url: str,
        item_id: str,
        info_dict: dict,
        audio_path: Path,
        duration: float,
        batch_num: int,
    ) -> dict:
        """Xây dựng record JSON theo spec."""
        video_id = item_id.removeprefix("tt_")

        # Platform meta
        track = info_dict.get("track", "") or ""
        original_keywords = {"original sound", "âm thanh gốc", "tiếng động gốc", ""}
        music_is_original = track.lower() in original_keywords

        platform_meta = {
            "music_is_original": music_is_original,
            "is_duet": "duet" in (info_dict.get("description", "") or "").lower(),
            "is_stitch": "stitch" in (info_dict.get("description", "") or "").lower(),
            "has_platform_captions": bool(info_dict.get("subtitles")),
        }

        # posted_at
        timestamp = info_dict.get("timestamp")
        if timestamp:
            posted_at = datetime.fromtimestamp(
                timestamp, tz=VN_TZ
            ).isoformat(timespec="seconds")
        else:
            posted_at = None

        # audio_path relative
        try:
            rel_path = audio_path.relative_to(BASE_OUTPUT_DIR)
            audio_rel = str(rel_path).replace("\\", "/")
        except ValueError:
            audio_rel = str(audio_path)

        return {
            "item_id": item_id,
            "platform": "tiktok",
            "platform_video_id": video_id,
            "video_url": url,
            "title": info_dict.get("title", "") or "",
            "description": info_dict.get("description", "") or "",
            "posted_at": posted_at,
            "language_raw": "vi",
            "audio_path": audio_rel,
            "duration_seconds": round(duration, 3),
            "crawl_batch": make_batch_id("tiktok", batch_num),
            "crawled_at": datetime.now(VN_TZ).isoformat(timespec="seconds"),
            "platform_meta": platform_meta,
            "_track": track,  # Internal field cho music_detector
        }
