"""
processors/cloud_speech_api.py — Module nhận diện giọng nói & phương ngữ qua Cloud AI API & Fallback Local.

Cơ chế Quota Circuit Breaker tự động:
  - Khi phát hiện HTTP 429 (Rate Limit / Quota Exhausted / Resource Exhausted),
    hệ thống tự động vô hiệu hóa Cloud Provider đó và chuyển sang Provider tiếp theo.
  - Nếu tất cả Cloud Provider hết quota -> Tự động chuyển 100% sang LOCAL (faster-whisper),
    đảm bảo đợt cào tiếp tục chạy trơn tru mà không bị crash hay gián đoạn.
"""

import os
import json
import base64
import time
from pathlib import Path
from typing import Optional
import requests

from utils.logger import get_logger

logger = get_logger("cloud_speech_api")


class CloudSpeechAPI:
    """
    Client đa nền tảng gọi API nhận diện giọng nói và phương ngữ vùng miền.
    Có tích hợp Circuit Breaker tự động chuyển Local khi hết Quota.
    """

    GROQ_TRANS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

    OPENAI_TRANS_URL = "https://api.openai.com/v1/audio/transcriptions"
    OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

    GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    # Tập hợp các provider đã bị hết quota trong phiên chạy này
    _exhausted_providers: set[str] = set()

    def __init__(
        self,
        provider: str = "auto",
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        timeout_sec: int = 30,
    ) -> None:
        self.provider = provider or "auto"
        self.groq_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
        self.gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
        self.openai_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.timeout = timeout_sec

        self.active_provider = self._determine_provider()
        logger.info(f"[CloudSpeechAPI] Khởi tạo thành công: active_provider='{self.active_provider}'")

    @classmethod
    def _is_quota_error(cls, status_code: int, error_text: str) -> bool:
        """Kiểm tra phản hồi có phải lỗi hết hạn mức (Quota / Rate Limit) không."""
        if status_code in (429, 402, 403):
            return True
        err_lower = error_text.lower()
        keywords = [
            "quota", "rate limit", "resource_exhausted", "too many requests",
            "insufficient_quota", "exceeded your current quota", "billing"
        ]
        return any(kw in err_lower for kw in keywords)

    @classmethod
    def mark_exhausted(cls, provider: str, reason: str = "") -> None:
        """Đánh dấu provider đã hết quota và kích hoạt chuyển sang Local."""
        if provider not in cls._exhausted_providers and provider != "local":
            cls._exhausted_providers.add(provider)
            logger.warning(
                f"[CloudSpeechAPI] ⚠️ HẾT QUOTA / RATE LIMIT từ '{provider}' ({reason})! "
                f"Tự động ngắt '{provider}' và chuyển sang fallback an toàn."
            )

    def _determine_provider(self) -> str:
        """Xác định provider tối ưu còn quota."""
        if self.provider != "auto":
            if self.provider in self._exhausted_providers:
                logger.info(f"[CloudSpeechAPI] Provider chỉ định '{self.provider}' đã hết quota -> Chuyển LOCAL.")
                return "local"
            return self.provider

        if self.groq_key and "groq" not in self._exhausted_providers:
            return "groq"
        if self.gemini_key and "gemini" not in self._exhausted_providers:
            return "gemini"
        if self.openai_key and "openai" not in self._exhausted_providers:
            return "openai"

        if self._exhausted_providers:
            logger.info(
                f"[CloudSpeechAPI] 🔄 Toàn bộ Cloud AI ({', '.join(self._exhausted_providers)}) "
                "đã hết quota. Đang kích hoạt 100% chế độ LOCAL (faster-whisper)."
            )
        return "local"

    # ─────────────────────────────────────────────────────────────
    # PHẦN 1: NHẬN DIỆN GIỌNG NÓI (SPEECH-TO-TEXT)
    # ─────────────────────────────────────────────────────────────

    def transcribe(self, audio_path: Path, language: str = "vi") -> dict:
        """
        Nhận diện giọng nói từ file WAV. Tự động chuyển Local nếu hết Quota.
        """
        if not audio_path.exists():
            return {"text": "", "provider": "none", "success": False, "error": f"File not found: {audio_path}"}

        t0 = time.monotonic()
        prov = self._determine_provider()

        # 1. Thử Groq API (whisper-large-v3)
        if (prov == "groq" or (self.provider == "auto" and self.groq_key)) and "groq" not in self._exhausted_providers:
            res = self._call_groq_transcribe(audio_path, language)
            if res.get("success"):
                res["duration_ms"] = int((time.monotonic() - t0) * 1000)
                return res
            if res.get("is_quota"):
                self.mark_exhausted("groq", res.get("error", ""))
            else:
                logger.warning(f"[CloudSpeechAPI] Groq STT thất bại ({res.get('error')}), thử provider khác...")

        # 2. Thử Gemini API
        if (prov == "gemini" or (self.provider == "auto" and self.gemini_key)) and "gemini" not in self._exhausted_providers:
            res = self._call_gemini_transcribe(audio_path)
            if res.get("success"):
                res["duration_ms"] = int((time.monotonic() - t0) * 1000)
                return res
            if res.get("is_quota"):
                self.mark_exhausted("gemini", res.get("error", ""))
            else:
                logger.warning(f"[CloudSpeechAPI] Gemini STT thất bại ({res.get('error')}), thử provider khác...")

        # 3. Thử OpenAI API
        if (prov == "openai" or (self.provider == "auto" and self.openai_key)) and "openai" not in self._exhausted_providers:
            res = self._call_openai_transcribe(audio_path, language)
            if res.get("success"):
                res["duration_ms"] = int((time.monotonic() - t0) * 1000)
                return res
            if res.get("is_quota"):
                self.mark_exhausted("openai", res.get("error", ""))
            else:
                logger.warning(f"[CloudSpeechAPI] OpenAI STT thất bại ({res.get('error')}), fallback local...")

        # 4. Fallback an toàn tuyệt đối về Local (faster-whisper)
        logger.info(f"[CloudSpeechAPI] 🛡️ Đang chạy LOCAL (faster-whisper) cho file {audio_path.name}")
        res = self._call_local_transcribe(audio_path, language)
        res["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return res

    def _call_groq_transcribe(self, audio_path: Path, language: str) -> dict:
        if not self.groq_key:
            return {"success": False, "error": "GROQ_API_KEY thiếu"}
        try:
            headers = {"Authorization": f"Bearer {self.groq_key}"}
            with open(audio_path, "rb") as f:
                files = {
                    "file": (audio_path.name, f, "audio/wav"),
                    "model": (None, "whisper-large-v3"),
                    "language": (None, language),
                    "response_format": (None, "json"),
                    "temperature": (None, "0.0"),
                }
                r = requests.post(self.GROQ_TRANS_URL, headers=headers, files=files, timeout=self.timeout)
            if r.status_code == 200:
                text = r.json().get("text", "").strip()
                return {"text": text, "provider": "groq", "model": "whisper-large-v3", "success": True}
            
            is_quota = self._is_quota_error(r.status_code, r.text)
            return {"success": False, "error": f"Groq HTTP {r.status_code}: {r.text[:200]}", "is_quota": is_quota}
        except Exception as exc:
            is_quota = self._is_quota_error(0, str(exc))
            return {"success": False, "error": str(exc), "is_quota": is_quota}

    def _call_gemini_transcribe(self, audio_path: Path) -> dict:
        if not self.gemini_key:
            return {"success": False, "error": "GEMINI_API_KEY thiếu"}
        try:
            url = f"{self.GEMINI_BASE_URL}?key={self.gemini_key}"
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Hãy nghe đoạn âm thanh này và xuất ra toàn bộ transcript tiếng Việt một cách chính xác nhất. Chỉ trả về duy nhất nội dung transcript đã nhận diện."},
                        {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}}
                    ]
                }],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024}
            }
            r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=self.timeout)
            if r.status_code == 200:
                data = r.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                return {"text": text, "provider": "gemini", "model": "gemini-2.0-flash", "success": True}
            
            is_quota = self._is_quota_error(r.status_code, r.text)
            return {"success": False, "error": f"Gemini HTTP {r.status_code}: {r.text[:200]}", "is_quota": is_quota}
        except Exception as exc:
            is_quota = self._is_quota_error(0, str(exc))
            return {"success": False, "error": str(exc), "is_quota": is_quota}

    def _call_openai_transcribe(self, audio_path: Path, language: str) -> dict:
        if not self.openai_key:
            return {"success": False, "error": "OPENAI_API_KEY thiếu"}
        try:
            headers = {"Authorization": f"Bearer {self.openai_key}"}
            with open(audio_path, "rb") as f:
                files = {
                    "file": (audio_path.name, f, "audio/wav"),
                    "model": (None, "whisper-1"),
                    "language": (None, language),
                    "response_format": (None, "json"),
                    "temperature": (None, "0.0"),
                }
                r = requests.post(self.OPENAI_TRANS_URL, headers=headers, files=files, timeout=self.timeout)
            if r.status_code == 200:
                text = r.json().get("text", "").strip()
                return {"text": text, "provider": "openai", "model": "whisper-1", "success": True}
            
            is_quota = self._is_quota_error(r.status_code, r.text)
            return {"success": False, "error": f"OpenAI HTTP {r.status_code}: {r.text[:200]}", "is_quota": is_quota}
        except Exception as exc:
            is_quota = self._is_quota_error(0, str(exc))
            return {"success": False, "error": str(exc), "is_quota": is_quota}

    def _call_local_transcribe(self, audio_path: Path, language: str) -> dict:
        try:
            from processors.transcription_broker import TranscriptionBroker
            broker = TranscriptionBroker()
            res = broker.get_or_transcribe(audio_path, model_size="base", language=language)
            return {
                "text": res.text,
                "provider": "local",
                "model": "faster-whisper-base",
                "success": res.success,
                "error": res.error,
            }
        except Exception as exc:
            return {"text": "", "provider": "local", "success": False, "error": str(exc)}

    # ─────────────────────────────────────────────────────────────
    # PHẦN 2: NHẬN DIỆN PHƯƠNG NGỮ VÙNG MIỀN (REGIONAL DIALECT AI)
    # ─────────────────────────────────────────────────────────────

    def classify_region(
        self,
        audio_path: Optional[Path] = None,
        transcript: str = "",
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Nhận diện phương ngữ vùng miền. Tự động fallback nếu hết Quota.
        """
        # 1. Thử Gemini Multimodal (nếu chưa cạn quota)
        if self.gemini_key and "gemini" not in self._exhausted_providers and audio_path and audio_path.exists():
            res = self._call_gemini_region(audio_path, transcript, metadata)
            if res.get("success"):
                return res
            if res.get("is_quota"):
                self.mark_exhausted("gemini", res.get("error", ""))

        # 2. Thử Groq LLaMA 3.3 (nếu chưa cạn quota)
        if self.groq_key and "groq" not in self._exhausted_providers and (transcript or metadata):
            res = self._call_groq_region(transcript, metadata)
            if res.get("success"):
                return res
            if res.get("is_quota"):
                self.mark_exhausted("groq", res.get("error", ""))

        # 3. Thử OpenAI (nếu chưa cạn quota)
        if self.openai_key and "openai" not in self._exhausted_providers and (transcript or metadata):
            res = self._call_openai_region(transcript, metadata)
            if res.get("success"):
                return res
            if res.get("is_quota"):
                self.mark_exhausted("openai", res.get("error", ""))

        # Khi hết Cloud Quota -> Trả về success=False để RegionClassifier dùng Local Rules
        return {
            "region": "mixed",
            "confidence": 0.0,
            "provider": "local_fallback",
            "reason": "Cloud AI Quota exhausted or not configured -> using local rules",
            "success": False
        }

    def _call_gemini_region(self, audio_path: Path, transcript: str, metadata: Optional[dict]) -> dict:
        try:
            url = f"{self.GEMINI_BASE_URL}?key={self.gemini_key}"
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

            prompt = (
                "Bạn là chuyên gia ngôn ngữ học tiếng Việt. Hãy lắng nghe đoạn âm thanh này để xác định chất giọng / phương ngữ vùng miền của người nói chính. "
                f"Transcript: {transcript[:400]}. "
                "Quy chuẩn đầu ra: Chỉ chọn 1 trong 4 nhãn: 'northern' (Bắc), 'central' (Trung), 'southern' (Nam), 'mixed' (Pha trộn). "
                "Trả về duy nhất định dạng JSON: {\"region\": \"northern\"|\"central\"|\"southern\"|\"mixed\", \"confidence\": 0.95, \"reason\": \"lý do ngắn gọn\"}"
            )

            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}}
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "responseMimeType": "application/json",
                }
            }

            r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=self.timeout)
            if r.status_code == 200:
                data = r.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                raw_json = "".join(p.get("text", "") for p in parts).strip()
                parsed = json.loads(raw_json)
                reg = parsed.get("region", "mixed").lower()
                if reg not in {"northern", "central", "southern", "mixed"}:
                    reg = "mixed"
                return {
                    "region": reg,
                    "confidence": float(parsed.get("confidence", 0.9)),
                    "reason": parsed.get("reason", "Gemini Multimodal Audio Analysis"),
                    "provider": "gemini",
                    "success": True,
                }
            is_quota = self._is_quota_error(r.status_code, r.text)
            return {"success": False, "error": f"Gemini HTTP {r.status_code}", "is_quota": is_quota}
        except Exception as exc:
            is_quota = self._is_quota_error(0, str(exc))
            return {"success": False, "error": str(exc), "is_quota": is_quota}

    def _call_groq_region(self, transcript: str, metadata: Optional[dict]) -> dict:
        try:
            headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json",
            }
            channel_info = ""
            if metadata:
                channel_info = f"Kênh: {metadata.get('channel', '')} | Tiêu đề: {metadata.get('title', '')}"

            prompt = (
                "Bạn là chuyên gia phương ngữ tiếng Việt. Hãy xác định vùng miền của người nói dựa vào transcript và thông tin kênh sau. "
                f"{channel_info}. "
                f"Transcript: \"{transcript[:1000]}\". "
                "Quy tắc phân loại: "
                "'northern': Dùng từ ngữ miền Bắc (thế này, chả, nhở, đằng ấy, ngô, muôi, cốc, bát, lợn, đài TH miền Bắc...). "
                "'central': Dùng từ ngữ miền Trung (chi, mô, tê, răng, rứa, trốc cú, chộ, ngó, chừ, nớ, hỉ, trự, bơ...). "
                "'southern': Dùng từ ngữ miền Nam (vầy nè, hổng, hén, bển, bắp, vá, ly, chén, heo, dữ dằn, xỉu up xỉu down, đài TH miền Nam...). "
                "'mixed': Pha trộn hoặc trung tính toàn dân không có dấu ấn địa phương rõ nét. "
                "Chỉ trả về JSON hợp lệ: {\"region\": \"northern\"|\"central\"|\"southern\"|\"mixed\", \"confidence\": 0.95, \"reason\": \"lý do ngắn gọn\"}"
            )

            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "You are an expert Vietnamese dialectologist. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            }

            r = requests.post(self.GROQ_CHAT_URL, headers=headers, json=payload, timeout=self.timeout)
            if r.status_code == 200:
                parsed = json.loads(r.json()["choices"][0]["message"]["content"])
                reg = parsed.get("region", "mixed").lower()
                if reg not in {"northern", "central", "southern", "mixed"}:
                    reg = "mixed"
                return {
                    "region": reg,
                    "confidence": float(parsed.get("confidence", 0.9)),
                    "reason": parsed.get("reason", "Groq LLaMA-3.3 Linguistic Analysis"),
                    "provider": "groq",
                    "success": True,
                }
            is_quota = self._is_quota_error(r.status_code, r.text)
            return {"success": False, "error": f"Groq HTTP {r.status_code}", "is_quota": is_quota}
        except Exception as exc:
            is_quota = self._is_quota_error(0, str(exc))
            return {"success": False, "error": str(exc), "is_quota": is_quota}

    def _call_openai_region(self, transcript: str, metadata: Optional[dict]) -> dict:
        try:
            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json",
            }
            prompt = (
                "Phân loại phương ngữ tiếng Việt của transcript sau thành 1 trong 4 nhãn: 'northern', 'central', 'southern', 'mixed'. "
                f"Transcript: \"{transcript[:1000]}\". "
                "Trả về JSON: {\"region\": \"...\", \"confidence\": 0.95, \"reason\": \"...\"}"
            )
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            }
            r = requests.post(self.OPENAI_CHAT_URL, headers=headers, json=payload, timeout=self.timeout)
            if r.status_code == 200:
                parsed = json.loads(r.json()["choices"][0]["message"]["content"])
                reg = parsed.get("region", "mixed").lower()
                if reg not in {"northern", "central", "southern", "mixed"}:
                    reg = "mixed"
                return {
                    "region": reg,
                    "confidence": float(parsed.get("confidence", 0.9)),
                    "reason": parsed.get("reason", "OpenAI gpt-4o-mini"),
                    "provider": "openai",
                    "success": True,
                }
            is_quota = self._is_quota_error(r.status_code, r.text)
            return {"success": False, "error": f"OpenAI HTTP {r.status_code}", "is_quota": is_quota}
        except Exception as exc:
            is_quota = self._is_quota_error(0, str(exc))
            return {"success": False, "error": str(exc), "is_quota": is_quota}