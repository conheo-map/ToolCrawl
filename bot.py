#!/usr/bin/env python3
"""
bot.py — Telegram Bot Receiver & Remote Crawler Controller.

Cho phép gửi link TikTok / Facebook trực tiếp từ điện thoại vào Telegram.
Hệ thống tự động tải, convert WAV 16kHz Mono, chạy Hybrid AI tách nhạc,
lưu vào dataset và phản hồi tiến độ về điện thoại theo thời gian thực!

Cách chạy:
  python bot.py --token "YOUR_TELEGRAM_BOT_TOKEN"
Hoặc đặt biến môi trường:
  $env:TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
  python bot.py
"""

import argparse
import json
import os
import re
import sys
import time
import requests
from pathlib import Path
from datetime import datetime

import config as cfg
from crawlers.tiktok import TikTokCrawler
from crawlers.facebook import FacebookCrawler
from processors.music_detector import MusicDetector
from processors.vocal_separator import VocalSeparator
from processors.audio_enhancer import SpeechEnhancer
from processors.speech_transcriber import SpeechTranscriber
from storage.dedup import DedupStore
from storage.metadata_writer import MetadataWriter
from storage.state_manager import StateManager
from utils.logger import get_logger

logger = get_logger("telegram_bot")

URL_REGEX = re.compile(
    r'(https?://(?:www\.|vt\.|vm\.)?(?:tiktok\.com|facebook\.com|fb\.watch)/[^\s]+)',
    re.IGNORECASE,
)


class TelegramCrawlerBot:
    def __init__(self, token: str, allowed_users: list[int] | None = None) -> None:
        self._token = token
        self._api_url = f"https://api.telegram.org/bot{token}"
        self._allowed_users = allowed_users or []
        self._offset = 0
        self._running = True

        # Pipeline components
        cookie_file = Path("cookies_tiktok.txt")
        self._cookies = cookie_file if cookie_file.exists() else None
        self._tt_crawler = TikTokCrawler(cookies_file=self._cookies)
        self._fb_crawler = FacebookCrawler()

        self._dedup = DedupStore()
        self._tt_state = StateManager(platform="tiktok")
        self._fb_state = StateManager(platform="facebook")
        self._music_detector = MusicDetector()
        self._vocal_separator = VocalSeparator()
        self._speech_enhancer = SpeechEnhancer()
        self._writer = MetadataWriter(
            metadata_file=cfg.METADATA_FILE,
            summary_file=cfg.SUMMARY_FILE,
        )
        self._music_detector = MusicDetector(enabled=cfg.MUSIC_FILTER_ENABLED)
        self._vocal_separator = VocalSeparator()
        self._speech_enhancer = SpeechEnhancer()
        self._speech_transcriber = SpeechTranscriber()

        # Tự động gỡ Webhook Cloud để máy tính Local có thể nhận tin nhắn
        self._clear_webhook()

        logger.info("Telegram Crawler Bot initialized successfully!")

    def _clear_webhook(self) -> None:
        """Tự động chuyển tiếp tin nhắn về máy Local."""
        try:
            url = f"{self._api_url}/deleteWebhook"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                logger.info("⚡ Đã chuyển quyền điều khiển Telegram về máy tính Local!")
        except Exception as exc:
            logger.debug(f"Clear webhook notice: {exc}")

    def send_message(self, chat_id: int | str, text: str, parse_mode: str = "Markdown") -> None:
        """Gửi tin nhắn phản hồi về Telegram của người dùng."""
        try:
            url = f"{self._api_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as exc:
            logger.warning(f"Failed to send Telegram message: {exc}")

    def get_updates(self) -> list[dict]:
        """Lấy danh sách tin nhắn mới từ Telegram (Long polling)."""
        try:
            url = f"{self._api_url}/getUpdates"
            params = {"offset": self._offset, "timeout": 20}
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result", [])
        except Exception as exc:
            logger.debug(f"getUpdates error: {exc}")
        return []

    DEFAULT_WEBHOOK_URL = "https://saydi-telegram-bridge.cuctranthu38.workers.dev"

    def _restore_webhook(self) -> None:
        """Tự động kích hoạt lại Webhook Cloud khi tắt bot trên máy tính."""
        try:
            url = f"{self._api_url}/setWebhook"
            payload = {"url": self.DEFAULT_WEBHOOK_URL}
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200 and resp.json().get("ok"):
                logger.info("☁️ ĐÃ TỰ ĐỘNG KHÔI PHỤC WEBHOOK CHO CLOUD (GitHub Actions sẵn sàng khi bạn tắt máy)!")
        except Exception as exc:
            logger.debug(f"Restore webhook notice: {exc}")

    def start(self) -> None:
        """Khởi động vòng lặp lắng nghe tin nhắn từ điện thoại."""
        logger.info("🤖 Bot đang chạy và sẵn sàng nhận link từ Telegram! (Bấm Ctrl+C để dừng)")
        print("\n" + "=" * 60)
        print("🤖 TELEGRAM BOT SẴN SÀNG NHẬN LINK TRÊN LOCAL!")
        print("Gửi link TikTok/Facebook từ điện thoại vào Telegram Bot để cào tự động.")
        print("Khi bạn bấm Ctrl+C để tắt, hệ thống sẽ TỰ ĐỘNG chuyển giao lại cho Cloud!")
        print("=" * 60 + "\n")

        try:
            while self._running:
                try:
                    updates = self.get_updates()
                    for update in updates:
                        self._offset = update["update_id"] + 1
                        message = update.get("message")
                        if not message:
                            continue

                        self._handle_message(message)
                except KeyboardInterrupt:
                    logger.info("Shutting down local bot...")
                    self._running = False
                    break
                except Exception as exc:
                    logger.error(f"Unexpected error in bot loop: {exc}")
                    time.sleep(2)
        finally:
            self._restore_webhook()

    def _handle_message(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        user_id = message.get("from", {}).get("id")
        user_name = message.get("from", {}).get("first_name", "Bạn")
        text = message.get("text", "").strip()

        # Kiểm tra quyền truy cập (nếu có cấu hình giới hạn)
        if self._allowed_users and user_id not in self._allowed_users:
            self.send_message(
                chat_id,
                f"⛔ *Từ chối truy cập!* ID của bạn (`{user_id}`) chưa được cấp quyền.",
            )
            return

        if not text:
            return

        # ─── Xử lý các lệnh Slash Commands ───
        if text.startswith("/start") or text.startswith("/help"):
            help_msg = (
                f"👋 *Xin chào {user_name}!* Chào mừng bạn đến với *Saydi Audio Crawler Bot*.\n\n"
                "📌 *CÁCH DÙNG RẤT ĐƠN GIẢN:*\n"
                "• Lướt TikTok / Facebook thấy video hay, bấm **Chia sẻ ➔ Sao chép liên kết** rồi dán thẳng vào đây.\n"
                "• Bạn có thể gửi 1 link hoặc gửi nhiều link cùng lúc (mỗi link 1 dòng).\n"
                "• Hệ thống sẽ tự động tải, chuyển WAV 16kHz mono, bóc tách nhạc AI và báo cáo kết quả!\n\n"
                "📊 *CÁC LỆNH KHÁC:*\n"
                "• `/stats` — Xem thống kê tổng số video & số giờ audio đã cào hôm nay.\n"
                "• `/help` — Xem hướng dẫn này."
            )
            self.send_message(chat_id, help_msg)
            return

        if text.startswith("/stats"):
            self._handle_stats_command(chat_id)
            return

        # ─── Xử lý danh sách link URLs ───
        found_urls = URL_REGEX.findall(text)
        if not found_urls:
            self.send_message(
                chat_id,
                "ℹ️ Không tìm thấy link TikTok hoặc Facebook hợp lệ trong tin nhắn của bạn. Vui lòng gửi lại link!",
            )
            return

        self.send_message(
            chat_id,
            f"📥 *Đã nhận {len(found_urls)} link!* Đang bắt đầu xử lý qua Pipeline Hybrid AI...",
        )

        success_count = 0
        skip_count = 0
        error_count = 0

        for idx, url in enumerate(found_urls, start=1):
            is_tiktok = "tiktok.com" in url.lower()
            platform_name = "TikTok" if is_tiktok else "Facebook"
            crawler = self._tt_crawler if is_tiktok else self._fb_crawler
            state = self._tt_state if is_tiktok else self._fb_state

            # Thông báo bắt đầu xử lý link
            self.send_message(
                chat_id,
                f"⏳ *[{idx}/{len(found_urls)}] Đang tải {platform_name}:*\n`{url}`",
            )

            try:
                record = crawler.crawl_url(url, batch_num=1)
                if not record:
                    error_count += 1
                    self.send_message(
                        chat_id,
                        f"❌ *[{idx}/{len(found_urls)}] Thất bại:* Không thể trích xuất dữ liệu từ link này.",
                    )
                    continue

                item_id = record["item_id"]
                audio_path = cfg.AUDIO_DIR / f"{item_id}.wav"

                # Check Dedup
                if self._dedup.is_seen(item_id):
                    skip_count += 1
                    if audio_path.exists():
                        audio_path.unlink(missing_ok=True)
                    self.send_message(
                        chat_id,
                        f"⚠️ *[{idx}/{len(found_urls)}] Đã cào trước đây (Bỏ qua trùng lặp):*\nID: `{item_id}`",
                    )
                    continue

                # Hybrid Pipeline: Tách nhạc AI
                music_status = self._music_detector.process(audio_path=audio_path, metadata=record)
                clean_tag = "Âm thanh gốc sạch"

                if music_status == "music":
                    if self._vocal_separator.available:
                        success = self._vocal_separator.separate(audio_path)
                        if success:
                            record["vocal_separated"] = True
                            record["clean_method"] = "demucs_ai"
                            clean_tag = "Đã lọc sạch nhạc nền bằng AI"
                        else:
                            self._music_detector.quarantine(audio_path)
                            self._dedup.mark_seen(item_id)
                            state.mark_done(url)
                            skip_count += 1
                            self.send_message(
                                chat_id,
                                f"⚠️ *[{idx}/{len(found_urls)}] Nhạc nền quá lớn, không tách được -> Đã chuyển quarantine:* `{item_id}`",
                            )
                            continue
                    else:
                        self._music_detector.quarantine(audio_path)
                        self._dedup.mark_seen(item_id)
                        state.mark_done(url)
                        skip_count += 1
                        self.send_message(
                            chat_id,
                            f"⚠️ *[{idx}/{len(found_urls)}] Có nhạc nền -> Đã chuyển quarantine:* `{item_id}`",
                        )
                        continue
                else:
                    record["vocal_separated"] = False
                    record["clean_method"] = "original"

                # Tăng cường âm thanh: Khử tạp âm, tăng độ rõ chữ & cân bằng âm lượng
                if self._speech_enhancer.enhance(audio_path):
                    from processors.audio_converter import verify_audio
                    try:
                        final_info = verify_audio(audio_path)
                        record["duration_seconds"] = final_info["duration_seconds"]
                    except Exception as e:
                        logger.warning(f"Failed to recalculate duration for {item_id}: {e}")

                # Bước 05: Sinh transcript tiếng Việt nháp (Lưu trên Local)
                extended_data = {}
                trans_info = self._speech_transcriber.transcribe_file(
                    audio_path,
                    output_dir=Path("local_research") / cfg.CRAWL_DATE / "transcripts"
                )
                if trans_info.get("text"):
                    extended_data["transcript_raw"] = trans_info["text"]
                    extended_data["transcript_word_count"] = trans_info["word_count"]

                # Ghi Metadata & Checkpoint (metadata.json cho Drive, metadata_extended.json cho Local)
                record.pop("_track", None)
                self._writer.add_record(record, extended_info=extended_data)
                self._dedup.mark_seen(item_id)
                state.mark_done(url)
                success_count += 1

                # Phản hồi thành công
                success_msg = (
                    f"✅ *[{idx}/{len(found_urls)}] HOÀN TẤT THÀNH CÔNG!*\n"
                    f"• **Item ID:** `{item_id}`\n"
                    f"• **Thời lượng:** `{record['duration_seconds']:.1f}s` (Chuẩn 16kHz Mono)\n"
                    f"• **Trạng thái:** {clean_tag}\n"
                    f"• **File:** `audio/{item_id}.wav`"
                )
                self.send_message(chat_id, success_msg)

            except Exception as exc:
                error_count += 1
                logger.error(f"Error crawling URL from Telegram: {url} — {exc}")
                self.send_message(
                    chat_id,
                    f"❌ *[{idx}/{len(found_urls)}] Lỗi xử lý:* `{str(exc)[:200]}`",
                )

        # Lưu checkpoint & ghi tổng kết
        self._dedup.save()
        self._writer.write_summary(platform="mixed", batch_count=1)

        # Tổng kết đợt gửi
        summary_msg = (
            f"🎉 *TỔNG KẾT ĐỢT CÀO:*\n"
            f"• ✅ Thành công: **{success_count}**\n"
            f"• ⏭️ Bỏ qua (Trùng/Quarantine): **{skip_count}**\n"
            f"• ❌ Lỗi: **{error_count}**\n"
            f"📁 Đã lưu vào `Week2/{cfg.CRAWL_DATE}/audio/` và đang tự động đồng bộ lên Google Drive..."
        )
        self.send_message(chat_id, summary_msg)

        # Tự động đẩy lên Google Drive
        try:
            from main import sync_to_gdrive
            sync_to_gdrive(cfg.WEEK_NUMBER)
        except Exception as exc:
            logger.debug(f"Bot Google Drive sync notice: {exc}")

    def _handle_stats_command(self, chat_id: int | str) -> None:
        """Đọc và gửi thống kê dataset hôm nay."""
        if not cfg.SUMMARY_FILE.exists():
            self.send_message(
                chat_id,
                f"📊 *Chưa có dữ liệu cào cho ngày {cfg.CRAWL_DATE}.*",
            )
            return

        try:
            summary = json.loads(cfg.SUMMARY_FILE.read_text(encoding="utf-8"))
            items = summary.get("items_delivered", 0)
            hours = summary.get("total_hours", 0.0)
            vocal_sep = summary.get("vocal_separated_count", 0)
            errors = summary.get("error_count", 0)

            stats_msg = (
                f"📊 *THỐNG KÊ DỮ LIỆU NGÀY {cfg.CRAWL_DATE}:*\n\n"
                f"• 🎯 Tổng số audio sạch: **{items} file**\n"
                f"• ⏱️ Tổng thời lượng: **{hours:.2f} giờ**\n"
                f"• 🎵 Số file đã qua AI tách nhạc: **{vocal_sep} file**\n"
                f"• ⚠️ Số lượt lỗi: **{errors}**\n"
                f"• 🎼 Chuẩn Audio: `16000Hz, 1ch, WAV PCM 16-bit`\n\n"
                f"📁 Thư mục: `Week2/{cfg.CRAWL_DATE}/`"
            )
            self.send_message(chat_id, stats_msg)
        except Exception as exc:
            self.send_message(chat_id, f"❌ Lỗi khi đọc summary: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SaydiTool Telegram Bot Crawler")
    parser.add_argument(
        "--token",
        type=str,
        default=cfg.TELEGRAM_BOT_TOKEN,
        help="Telegram Bot Token lấy từ @BotFather",
    )
    args = parser.parse_args()

    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("\n" + "=" * 60)
        print("❌ CHƯA CÓ TELEGRAM BOT TOKEN!")
        print("=" * 60)
        print("Cách lấy token miễn phí trong 1 phút:")
        print("1. Mở Telegram, tìm kiếm bot: @BotFather")
        print("2. Gõ lệnh: /newbot -> Đặt tên cho bot của bạn")
        print("3. Copy mã Token dạng: 123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
        print("4. Chạy bot bằng lệnh:")
        print("   python bot.py --token \"MA_TOKEN_CUA_BAN\"")
        print("=" * 60 + "\n")
        sys.exit(1)

    bot = TelegramCrawlerBot(token=token, allowed_users=cfg.TELEGRAM_ALLOWED_USERS)
    bot.start()


if __name__ == "__main__":
    main()
