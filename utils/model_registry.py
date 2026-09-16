"""
utils/model_registry.py — Thread-safe singleton registry cho tất cả AI model.
Đảm bảo mỗi model chỉ được load một lần duy nhất trong toàn bộ chương trình,
kể cả khi nhiều thread yêu cầu đồng thời (double-checked locking pattern).

Giải quyết:
  - Race condition khi 4 worker đồng thời khởi tạo Whisper (CUDA OOM)
  - Model được load 2-3 lần riêng biệt bởi SpeechMaster / RegionClassifier / QC
  - GPU semaphore để tối đa 1 Whisper inference tại một thời điểm (tránh VRAM OOM)
"""

import threading
from typing import Any, Callable
from utils.logger import get_logger

logger = get_logger("model_registry")


class ModelRegistry:
    """
    Singleton registry thread-safe cho AI model.
    Dùng double-checked locking để đảm bảo chỉ load 1 lần.
    """

    _models: dict[str, Any] = {}
    _model_locks: dict[str, threading.Lock] = {}
    _registry_lock: threading.Lock = threading.Lock()

    # GPU semaphore: tối đa 1 Whisper inference đồng thời (tránh CUDA OOM)
    # Thay đổi thành Semaphore(2) nếu VRAM >= 8GB và muốn tăng throughput
    gpu_semaphore: threading.Semaphore = threading.Semaphore(1)

    @classmethod
    def get(cls, model_key: str, loader_fn: Callable[[], Any]) -> Any:
        """
        Lấy model theo key. Nếu chưa có, gọi loader_fn() để load.
        Double-checked locking: kiểm tra không có lock -> có lock -> kiểm tra lần nữa.

        Args:
            model_key: Định danh duy nhất (vd: whisper_base, whisper_tiny, demucs_htdemucs)
            loader_fn: Hàm không tham số trả về model đã khởi tạo

        Returns:
            Model instance (được cache, tái dùng qua tất cả các lần gọi sau)
        """
        # Lần kiểm tra nhanh không có lock (fast path)
        if model_key in cls._models:
            return cls._models[model_key]

        # Lấy hoặc tạo per-key lock
        with cls._registry_lock:
            if model_key not in cls._model_locks:
                cls._model_locks[model_key] = threading.Lock()

        # Double-checked locking với per-key lock
        with cls._model_locks[model_key]:
            if model_key not in cls._models:
                logger.info(f"[ModelRegistry] Loading model: {model_key} ...")
                try:
                    model = loader_fn()
                    cls._models[model_key] = model
                    logger.info(f"[ModelRegistry] Model ready: {model_key}")
                except Exception as exc:
                    logger.error(f"[ModelRegistry] Failed to load {model_key}: {exc}")
                    raise

        return cls._models[model_key]

    @classmethod
    def release(cls, model_key: str) -> None:
        """
        Giải phóng model khỏi registry (dùng khi cần giải phóng VRAM).
        """
        with cls._registry_lock:
            if model_key in cls._models:
                del cls._models[model_key]
                logger.info(f"[ModelRegistry] Released: {model_key}")

    @classmethod
    def is_loaded(cls, model_key: str) -> bool:
        """Kiểm tra model đã được load chưa."""
        return model_key in cls._models

    @classmethod
    def list_loaded(cls) -> list[str]:
        """Danh sách model đang được cache."""
        return list(cls._models.keys())
