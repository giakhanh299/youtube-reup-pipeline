from __future__ import annotations

from pathlib import Path
from typing import Any

from processors.tts_engine import create_voice
from services.omnivoice_service import OmniVoiceService
from utils.retry import RetryStrategy


class TTSService:
    """TTS service wrapper around the current engine function."""

    def __init__(self, retry_strategy: RetryStrategy | None = None, logger: Any = None, settings: dict | None = None):
        self.retry_strategy = retry_strategy
        self.logger = logger
        self.settings = settings or {}

    def create_voice(self, text: str, output_file: Path, voice_cfg: dict, google_key_dir: str) -> None:
        engine = str(voice_cfg.get("tts_engine") or voice_cfg.get("engine") or "google").strip().lower()
        if engine == "omnivoice":
            operation = lambda: OmniVoiceService(
                model_name=voice_cfg.get("omnivoice_model_name") or self.settings.get("omnivoice_model_name", "k2-fsa/OmniVoice"),
                device=voice_cfg.get("omnivoice_device") or self.settings.get("omnivoice_device", "auto"),
                dtype=voice_cfg.get("omnivoice_dtype") or self.settings.get("omnivoice_dtype", "auto"),
            ).synthesize(text, output_file, voice_cfg)
            if self.retry_strategy:
                self.retry_strategy.run(operation, "tts_omnivoice_create_voice", "tts")
                return
            operation()
            return

        if self.retry_strategy:
            self.retry_strategy.run(
                lambda: create_voice(text, output_file, voice_cfg, google_key_dir),
                "tts_create_voice",
                "tts",
            )
            return
        create_voice(text, output_file, voice_cfg, google_key_dir)
