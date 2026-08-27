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
from config import TIKTOK_COOKIES_FILE, make_batch_id, BASE_OUTPUT_DIR, CRAWL_DATE

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
        Hỗ trợ:
          1. Direct video URL hoặc channel URL
          2. Đường dẫn file .txt chứa danh sách URLs
          3. Keyword tìm kiếm qua HTML scrape
        """
        urls: list[str] = []

        # Case 1: Channel URL hoặc @username
        if keyword.startswith("@") or ("tiktok.com/@" in keyword and "/video/" not in keyword):
            channel_urls = self._extract_channel_videos(keyword, max_results)
            if channel_urls:
                logger.info(f"[TikTok] Extracted {len(channel_urls)} videos from channel: {keyword}")
                return channel_urls[:max_results]

        # Case 2: Direct Video URL
        if keyword.startswith("http://") or keyword.startswith("https://"):
            resolved = self._resolve_url(keyword)
            if "/photo/" in resolved:
                logger.info(f"⏩ [TikTok] Tự động bỏ qua bài đăng ảnh (Photo Slideshow): {resolved}")
                return []
            if "/video/" in resolved or "vt.tiktok.com" in resolved:
                return [resolved]
            # Nếu là link kênh hoặc playlist khác
            channel_urls = self._extract_channel_videos(resolved, max_results)
            if channel_urls:
                logger.info(f"[TikTok] Extracted {len(channel_urls)} videos from URL: {keyword}")
                return channel_urls[:max_results]
            return [resolved]

        # Case 2: Text file of URLs
        keyword_path = Path(keyword)
        if keyword_path.exists() and keyword_path.is_file():
            lines = keyword_path.read_text(encoding="utf-8-sig").splitlines()
            loaded_entries = [
                line.strip().lstrip('\ufeff') for line in lines
                if line.strip() and not line.strip().lstrip('\ufeff').startswith("#")
            ]
            expanded_urls = []
            for entry in loaded_entries:
                if "/photo/" in entry:
                    continue
                if entry.startswith("@") or ("tiktok.com/@" in entry and "/video/" not in entry):
                    ch_vids = self._extract_channel_videos(entry, max_results=30)
                    expanded_urls.extend(ch_vids)
                else:
                    expanded_urls.append(entry)
            
            # Lọc bỏ tất cả link photo nếu có
            expanded_urls = [u for u in expanded_urls if "/photo/" not in u]
            logger.info(f"[TikTok] Loaded {len(loaded_entries)} entries from {keyword} -> expanded to {len(expanded_urls)} video URLs (Đã loại bỏ photo slideshows)")
            if max_results and max_results > 500:
                return expanded_urls[:max_results]
            # Nếu người dùng truyền file txt thì mặc định chạy toàn bộ file (không bị chặn ở 500)
            return expanded_urls if len(expanded_urls) > max_results and max_results == 500 else expanded_urls[:max_results]

        # Case 3: HTML scrape search
        try:
            urls = self._search_via_html(keyword, max_results)
            urls = [u for u in urls if "/photo/" not in u]
            logger.info(f"[TikTok] HTML scrape: {len(urls)} URLs for '{keyword}'")
        except Exception as exc:
            logger.error(f"[TikTok] Search failed for '{keyword}': {exc}")

        return urls[:max_results]

    def crawl_url(self, url: str, batch_num: int = 1) -> dict | None:
        """
        Crawl một URL TikTok:
          1. Resolve short link (vt.tiktok.com, vm.tiktok.com)
          2. Bỏ qua nếu là Photo post
          3. Download + convert audio
          4. Build record JSON theo spec
        Trả về None nếu lỗi.
        """
        url = self._resolve_url(url)
        if "/photo/" in url:
            logger.info(f"⏩ [TikTok] Tự động bỏ qua bài đăng ảnh (Photo Slideshow - không chứa giọng nói ASR): {url}")
            return None

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

    def _resolve_url(self, url: str) -> str:
        """Chuyển đổi short link (vt.tiktok.com) thành URL đầy đủ."""
        if "vt.tiktok.com" in url or "vm.tiktok.com" in url or "/t/" in url:
            try:
                import requests
                headers = self._proxy.get_ydl_headers()
                resp = requests.head(url, allow_redirects=True, timeout=10, headers=headers)
                if resp.url and resp.url != url:
                    logger.info(f"Resolved short URL {url} -> {resp.url}")
                    return resp.url
            except Exception as exc:
                logger.warning(f"Failed to resolve short URL {url}: {exc}")
        return url

    def _extract_channel_videos(self, channel_input: str, max_results: int = 100) -> list[str]:
        """
        Trích xuất danh sách URLs video từ trang profile kênh TikTok (@username).
        Quét trực tiếp video IDs được nhúng trong HTML profile.
        """
        import requests
        m = re.search(r'tiktok\.com/@([a-zA-Z0-9._-]+)', channel_input)
        if m:
            username = m.group(1)
        elif channel_input.startswith("@"):
            username = channel_input.lstrip("@")
        else:
            return []

        headers = self._proxy.get_ydl_headers()
        vids = set()

        # 1. Thử trích xuất qua yt-dlp flat extraction (lấy được danh sách video sâu hơn)
        try:
            opts = self._build_ydl_opts(download=False)
            opts["extract_flat"] = "in_playlist"
            opts["playlistend"] = max_results
            opts["quiet"] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.tiktok.com/@{username}", download=False)
                if info and "entries" in info:
                    for entry in info["entries"]:
                        if entry:
                            vid_url = entry.get("url") or entry.get("webpage_url") or ""
                            m_id = re.search(r'(\d{18,19})', str(vid_url))
                            if m_id:
                                vids.add(m_id.group(1))
        except Exception as exc:
            logger.debug(f"[TikTok] yt-dlp channel extract notice: {exc}")

        # 2. Quét từ trang Embed của kênh (Dự phòng nhanh nếu yt-dlp bị chặn)
        try:
            embed_url = f"https://www.tiktok.com/embed/@{username}"
            r_embed = requests.get(embed_url, headers=headers, timeout=10)
            if r_embed.status_code == 200:
                for vid in re.findall(r'/video/(\d{18,19})', r_embed.text):
                    vids.add(vid)
        except Exception as exc:
            logger.debug(f"[TikTok] Embed scrape error: {exc}")

        # 2. Quét từ trang Profile chính thức
        try:
            profile_url = f"https://www.tiktok.com/@{username}"
            r_prof = requests.get(profile_url, headers=headers, timeout=10)
            if r_prof.status_code == 200:
                for vid in re.findall(r'/video/(\d{18,19})', r_prof.text):
                    vids.add(vid)
                for vid in re.findall(r'["\'](?:itemId|videoId|aweme_id)["\']\s*:\s*["\'](\d{18,19})["\']', r_prof.text):
                    vids.add(vid)
        except Exception as exc:
            logger.debug(f"[TikTok] Profile scrape error: {exc}")

        urls = [f"https://www.tiktok.com/@{username}/video/{vid}" for vid in vids]
        if urls:
            logger.info(f"[TikTok] Trích xuất thành công {len(urls)} video từ kênh @{username}")
        else:
            logger.warning(f"[TikTok] Kênh @{username} chưa có video hoặc bị ẩn. Hãy dán link video vào urls.txt.")
        return urls[:max_results]

    def _build_ydl_opts(self, download: bool = True, output_dir: Path | None = None) -> dict:
        """Thêm API hostname bypass cho TikTok."""
        opts = super()._build_ydl_opts(download=download, output_dir=output_dir)
        opts["extractor_args"] = {
            "tiktok": {"api_hostname": ["api22-core-c-useast1a.tiktokv.com"]}
        }
        return opts

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

        # Pattern 1: standard @username/video/id
        for username, video_id in TIKTOK_VIDEO_PATTERN.findall(html):
            url = f"https://www.tiktok.com/@{username}/video/{video_id}"
            if url not in seen:
                seen.add(url)
                urls.append(url)

        # Pattern 2: video/id direct
        if not urls:
            direct_ids = re.findall(r'/video/(\d{15,})', html)
            for vid in direct_ids:
                url = f"https://www.tiktok.com/@user/video/{vid}"
                if url not in seen:
                    seen.add(url)
                    urls.append(url)

        # Pattern 3: itemStruct / JSON id
        if not urls:
            json_ids = re.findall(r'"id"\s*:\s*"(\d{15,})"', html)
            for vid in json_ids:
                url = f"https://www.tiktok.com/@user/video/{vid}"
                if url not in seen:
                    seen.add(url)
                    urls.append(url)

        return urls

    def _build_ydl_opts(self, download: bool = True, output_dir: Path | None = None) -> dict:
        """Inject TikTok mobile core API hostname để không bị lỗi hydration / webpage request."""
        opts = super()._build_ydl_opts(download=download, output_dir=output_dir)
        opts["extractor_args"] = {
            "tiktok": {
                "api_hostname": ["api22-core-c-useast1a.tiktokv.com", "api16-normal-c-useast1a.tiktokv.com"]
            }
        }
        return opts

    def _extract_item_id(self, url: str) -> str | None:
        """Extract item_id dạng tt_<video_id> từ URL (loại trừ photo)."""
        if "/photo/" in url:
            return None

        m = TIKTOK_VIDEO_PATTERN.search(url)
        if m:
            return f"tt_{m.group(2)}"
        
        # Check standard video pattern
        m_alt = re.search(r'/video/(\d{8,19})', url)
        if m_alt:
            return f"tt_{m_alt.group(1)}"

        # Resolve URL if not done
        resolved = self._resolve_url(url)
        if resolved != url:
            if "/photo/" in resolved:
                return None
            m_res = TIKTOK_VIDEO_PATTERN.search(resolved) or re.search(r'/video/(\d{8,19})', resolved)
            if m_res:
                return f"tt_{m_res.group(1 if len(m_res.groups()) == 1 else 2)}"

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
            "platform": "tiktok",
            "platform_video_id": video_id,
            "video_url": url,
            "title": title_text,
            "description": desc_text,
            "posted_at": posted_at,
            "language_raw": "vi",
            "audio_path": audio_rel,
            "duration_seconds": round(duration, 3),
            "crawl_batch": make_batch_id("tiktok", batch_num),
            "crawled_at": datetime.now(VN_TZ).isoformat(timespec="seconds"),
            "platform_meta": platform_meta,
            "language_region": region,
            "_track": track,  # Internal field cho music_detector
        }
