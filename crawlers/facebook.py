"""
crawlers/facebook.py — FacebookCrawler: search + metadata extraction + download.
"""

import re
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime, timezone, timedelta

import yt_dlp

from crawlers.base import BaseCrawler, DownloadError
from utils.logger import get_logger
from config import FACEBOOK_COOKIES_FILE, make_batch_id, BASE_OUTPUT_DIR, CRAWL_DATE

logger = get_logger("facebook_crawler")
VN_TZ = timezone(timedelta(hours=7))

# Patterns để extract Facebook video/reel ID
VIDEO_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'/reel/(\d{8,})'), "reel"),
    (re.compile(r'/videos/(?:[^/?#]+/)?(\d{8,})'), "video"),
    (re.compile(r'[?&]v=(\d{8,})'), "video"),
    (re.compile(r'"video_id"\s*:\s*"(\d{8,})"'), "video"),
    (re.compile(r'"videoId"\s*:\s*"(\d{8,})"'), "video"),
    (re.compile(r'story_fbid=(\d{8,})'), "video"),
]


class FacebookCrawler(BaseCrawler):
    PLATFORM = "facebook"
    ID_PREFIX = "fb"

    def __init__(self, cookies_file: Path | None = FACEBOOK_COOKIES_FILE, **kwargs):
        super().__init__(cookies_file=cookies_file, **kwargs)

    def search(self, keyword: str, max_results: int = 200) -> list[str]:
        """
        Tìm kiếm video/reels Facebook theo keyword.
        Hỗ trợ:
          1. Direct URL (Reel hoặc Video)
          2. File .txt chứa danh sách URLs
          3. Keyword tìm kiếm qua HTML scrape
        """
        # Case 1: Direct URL
        if keyword.startswith("http://") or keyword.startswith("https://"):
            return [keyword]

        # Case 2: File of URLs
        keyword_path = Path(keyword)
        if keyword_path.exists() and keyword_path.is_file():
            lines = keyword_path.read_text(encoding="utf-8-sig").splitlines()
            loaded = [
                line.strip().lstrip('\ufeff') for line in lines
                if line.strip() and not line.strip().lstrip('\ufeff').startswith("#")
            ]
            logger.info(f"[Facebook] Loaded {len(loaded)} URLs from file: {keyword}")
            return loaded[:max_results]

        # Case 3: Search HTML
        urls: list[str] = []
        try:
            urls = self._search_via_html(keyword, max_results)
            logger.info(f"[Facebook] Found {len(urls)} URLs for '{keyword}'")
        except Exception as exc:
            logger.error(f"[Facebook] Search failed for '{keyword}': {exc}")
        return urls[:max_results]

    def crawl_url(self, url: str, batch_num: int = 1) -> dict | None:
        """
        Crawl một URL Facebook:
          1. Download + convert audio
          2. Build record JSON theo spec
        """
        item_id, content_type = self._extract_item_id(url)
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
                content_type=content_type,
                info_dict=info_dict,
                audio_path=audio_path,
                duration=duration,
                batch_num=batch_num,
            )
            return record

        except DownloadError as exc:
            logger.error(f"[Facebook] Download failed for {item_id}: {exc}")
            return None
        except Exception as exc:
            logger.error(f"[Facebook] Unexpected error for {item_id}: {exc}")
            return None

    # ─────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────

    def _search_via_html(self, keyword: str, max_results: int) -> list[str]:
        """Scrape Facebook search page HTML."""
        search_url = (
            "https://www.facebook.com/search/videos/?q=" + quote_plus(keyword)
        )
        opts = self._build_ydl_opts(download=False)
        opts["quiet"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            response = ydl.urlopen(search_url)
            html = response.read().decode("utf-8", "replace")

        html = html.replace(r"\/", "/")
        seen: set[str] = set()
        urls: list[str] = []

        for pattern, kind in VIDEO_PATTERNS:
            for video_id in pattern.findall(html):
                if kind == "reel":
                    url = f"https://www.facebook.com/reel/{video_id}"
                else:
                    url = f"https://www.facebook.com/watch?v={video_id}"
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
                if len(urls) >= max_results:
                    return urls
        return urls

    def _extract_item_id(self, url: str) -> tuple[str | None, str]:
        """Extract (item_id, content_type) từ URL."""
        for pattern, kind in VIDEO_PATTERNS:
            m = pattern.search(url)
            if m:
                video_id = m.group(1)
                return f"fb_{video_id}", kind
        return None, "video"

    def _build_record(
        self,
        url: str,
        item_id: str,
        content_type: str,
        info_dict: dict,
        audio_path: Path,
        duration: float,
        batch_num: int,
    ) -> dict:
        """Xây dựng record JSON theo spec."""
        video_id = item_id.removeprefix("fb_")

        platform_meta = {
            "content_type": content_type,
            "has_platform_captions": bool(info_dict.get("subtitles")),
        }

        timestamp = info_dict.get("timestamp")
        if timestamp:
            posted_at = datetime.fromtimestamp(
                timestamp, tz=VN_TZ
            ).isoformat(timespec="seconds")
        else:
            posted_at = None

        # audio_path theo chuẩn spec
        audio_rel = f"audio/{item_id}.wav"

        # Phân loại vùng miền (northern / southern / central / mixed)
        from processors.region_classifier import RegionClassifier
        title_text = info_dict.get("title", "") or ""
        desc_text = info_dict.get("description", "") or ""
        uploader = info_dict.get("uploader", "") or info_dict.get("uploader_id", "") or info_dict.get("channel", "") or ""
        region = RegionClassifier.classify(
            title=title_text,
            description=desc_text,
            channel_name=uploader,
            audio_path=audio_path,
        )

        return {
            "item_id": item_id,
            "platform": "facebook",
            "platform_video_id": video_id,
            "video_url": url,
            "title": title_text,
            "description": desc_text,
            "posted_at": posted_at,
            "language_raw": "vi",
            "audio_path": audio_rel,
            "duration_seconds": round(duration, 3),
            "crawl_batch": make_batch_id("facebook", batch_num),
            "crawled_at": datetime.now(VN_TZ).isoformat(timespec="seconds"),
            "platform_meta": platform_meta,
            "language_region": region,
        }
